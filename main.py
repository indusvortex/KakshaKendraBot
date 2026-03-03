import os
from fastapi import FastAPI, Request, HTTPException, Response
from dotenv import load_dotenv

import database
from utils import generate_ai_response, send_whatsapp_message

load_dotenv()

app = FastAPI(title="WhatsApp AI Coach Bot")

# Verify Token used by Meta to verify webhook
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secure_verify_token")

@app.on_event("startup")
def on_startup():
    print("Initializing Database...")
    database.init_db()

@app.get("/webhook")
async def verify_webhook(request: Request):
    """
    Meta Challenge Verification.
    WhatsApp will send a GET request here when you configure the Webhook.
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
        
        # Check if it's a valid WhatsApp message
        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    
                    if "messages" in value:
                        for message in value["messages"]:
                            # Extract sender info and message content
                            sender_id = message["from"]  # Phone number
                            
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
                            
                            # 1. Save specific User Message to DB
                            database.save_message(sender_id, "user", message_text)
                            
                            # 2. Retrieve last 10 messages for context
                            history = database.get_recent_messages(sender_id, limit=10)
                            
                            # 3. Generate AI Response via Gemini
                            ai_response_text = generate_ai_response(history, message_text)
                            
                            # 4. Send back via WhatsApp API
                            send_whatsapp_message(sender_id, ai_response_text)
                            
                            # 5. Save AI's Response to DB
                            database.save_message(sender_id, "assistant", ai_response_text)
        return {"status": "success"}

    except Exception as e:
        print(f"Error processing webhook: {e}")
        # Always return 200 OK to WhatsApp so they don't retry repeatedly
        return {"status": "error"}

@app.get("/")
def health_check():
    return {"status": "Bot is running perfectly!"}
