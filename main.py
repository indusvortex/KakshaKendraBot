import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Response
from dotenv import load_dotenv

import database
from utils import generate_ai_response, send_whatsapp_message

load_dotenv()

# Verify Token used by Meta to verify webhook
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secure_verify_token")

# Track processed message IDs to avoid duplicate processing
# (WhatsApp can retry webhooks, sending the same message twice)
processed_message_ids: set = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing Database...")
    database.init_db()
    yield

app = FastAPI(title="WhatsApp AI Coach Bot", lifespan=lifespan)


@app.get("/webhook")
async def verify_webhook(request: Request):
    """
    Meta Challenge Verification.
    WhatsApp sends a GET request here when you configure the Webhook.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("WEBHOOK_VERIFIED")
            return Response(content=challenge, media_type="text/plain")
        else:
            raise HTTPException(status_code=403, detail="Verification token mismatch")
    return Response(content="Hello World", media_type="text/plain")


@app.post("/webhook")
async def handle_whatsapp_message(request: Request):
    """
    Receives incoming messages from WhatsApp.
    """
    try:
        body = await request.json()

        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})

                    if "messages" in value:
                        for message in value["messages"]:
                            # Deduplicate: skip if we already processed this message
                            message_id = message.get("id")
                            if message_id and message_id in processed_message_ids:
                                print(f"Skipping duplicate message: {message_id}")
                                continue
                            if message_id:
                                processed_message_ids.add(message_id)
                                # Prevent unbounded growth in memory
                                if len(processed_message_ids) > 10000:
                                    processed_message_ids.clear()

                            sender_id = message["from"]

                            if message["type"] == "text":
                                message_text = message["text"]["body"]
                            elif message["type"] == "interactive":
                                interactive = message["interactive"]
                                if interactive["type"] == "button_reply":
                                    message_text = interactive["button_reply"]["title"]
                                elif interactive["type"] == "list_reply":
                                    message_text = interactive["list_reply"]["title"]
                                else:
                                    continue
                            else:
                                continue

                            print(f"Received message from {sender_id}: {message_text}")

                            # 1. Fetch past history BEFORE saving current message
                            #    so the current message doesn't appear twice in the AI prompt
                            history = database.get_recent_messages(sender_id, limit=10)

                            # 2. Save current user message to DB
                            database.save_message(sender_id, "user", message_text)

                            # 3. Generate AI response (history = past only, message_text = current)
                            ai_response_text = generate_ai_response(history, message_text)

                            # 4. Send back via WhatsApp API
                            send_whatsapp_message(sender_id, ai_response_text)

                            # 5. Save AI response to DB
                            database.save_message(sender_id, "assistant", ai_response_text)

        return {"status": "success"}

    except Exception as e:
        print(f"Error processing webhook: {e}")
        # Always return 200 so WhatsApp doesn't retry endlessly
        return {"status": "error"}


@app.get("/")
def health_check():
    return {"status": "Bot is running perfectly!"}
