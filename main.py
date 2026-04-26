import os
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Response, Depends
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv

import database
from utils import generate_ai_response, send_whatsapp_message

load_dotenv()

# Verify Token used by Meta to verify webhook
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secure_verify_token")

# Admin credentials for /admin dashboard
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "kakshakendra2026")
security = HTTPBasic()


def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_pass = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

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


# ============================================================
# Admin Dashboard — view all student conversations
# ============================================================

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(user: str = Depends(verify_admin)):
    """Lists all student conversations with last message preview."""
    conversations = database.get_all_conversations()

    rows_html = ""
    if not conversations:
        rows_html = "<tr><td colspan='5' style='text-align:center;padding:40px;color:#888'>No conversations yet. Send 'Hi' to your bot to start!</td></tr>"
    else:
        for c in conversations:
            preview = (c["last_message"] or "")[:80].replace("<", "&lt;").replace(">", "&gt;")
            if len(c["last_message"] or "") > 80:
                preview += "..."
            role_badge = "BOT" if c["last_role"] == "assistant" else "STUDENT"
            badge_color = "#8b5cf6" if c["last_role"] == "assistant" else "#10b981"
            rows_html += f"""
            <tr onclick="window.location='/admin/chat/{c['sender_id']}'" style="cursor:pointer">
                <td><strong>+{c['sender_id']}</strong></td>
                <td><span style="background:{badge_color};color:white;padding:2px 8px;border-radius:4px;font-size:11px">{role_badge}</span></td>
                <td>{preview}</td>
                <td>{c['message_count']}</td>
                <td>{c['last_active']}</td>
            </tr>
            """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Kaksha Kendra Bot — Admin</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <style>
            body {{ font-family: -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 20px; }}
            h1 {{ margin: 0 0 20px; color: #fff; }}
            .stats {{ background: #1e293b; padding: 16px; border-radius: 8px; margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; }}
            th {{ background: #334155; padding: 12px; text-align: left; font-size: 12px; text-transform: uppercase; }}
            td {{ padding: 14px 12px; border-top: 1px solid #334155; font-size: 14px; }}
            tr:hover td {{ background: #334155; }}
            .refresh {{ background: #8b5cf6; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; }}
        </style>
    </head>
    <body>
        <h1>🎓 Kaksha Kendra Bot — Admin Dashboard</h1>
        <div class="stats">
            <strong>{len(conversations)} student conversations</strong>
            &nbsp;·&nbsp;
            <button class="refresh" onclick="location.reload()">↻ Refresh</button>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Phone</th>
                    <th>Last From</th>
                    <th>Last Message Preview</th>
                    <th>Total Msgs</th>
                    <th>Last Active</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </body>
    </html>
    """
    return html


@app.get("/admin/chat/{sender_id}", response_class=HTMLResponse)
def admin_chat_view(sender_id: str, user: str = Depends(verify_admin)):
    """Shows the full conversation with a specific student."""
    messages = database.get_full_conversation(sender_id)

    bubbles_html = ""
    for msg in messages:
        is_user = msg["role"] == "user"
        align = "flex-end" if is_user else "flex-start"
        bg = "#10b981" if is_user else "#334155"
        label = "STUDENT" if is_user else "BOT"
        content = msg["content"].replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        bubbles_html += f"""
        <div style="display:flex;justify-content:{align};margin:8px 0">
            <div style="max-width:70%;background:{bg};color:white;padding:10px 14px;border-radius:12px">
                <div style="font-size:10px;opacity:0.7;margin-bottom:4px">{label} · {msg['timestamp']}</div>
                <div>{content}</div>
            </div>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Chat with +{sender_id}</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <style>
            body {{ font-family: -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 20px; }}
            a {{ color: #a78bfa; text-decoration: none; }}
            h1 {{ margin: 0 0 8px; color: #fff; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/admin">← Back to all conversations</a>
            <h1>Chat with +{sender_id}</h1>
            <div style="color:#94a3b8;margin-bottom:20px">{len(messages)} total messages</div>
            <div>
                {bubbles_html}
            </div>
        </div>
    </body>
    </html>
    """
    return html


@app.get("/admin/api/conversations")
def admin_api_conversations(user: str = Depends(verify_admin)):
    """JSON endpoint listing all conversations."""
    return {"conversations": database.get_all_conversations()}
