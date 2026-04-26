import os
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Response, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
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
def admin_chat_view(sender_id: str, sent: str = "", error: str = "", user: str = Depends(verify_admin)):
    """Shows the full conversation with a specific student + send message form."""
    messages = database.get_full_conversation(sender_id)

    bubbles_html = ""
    for msg in messages:
        is_user = msg["role"] == "user"
        is_admin_msg = msg["content"].startswith("[ADMIN] ")
        content_clean = msg["content"][8:] if is_admin_msg else msg["content"]

        if is_user:
            align, bg, label = "flex-end", "#10b981", "STUDENT"
        elif is_admin_msg:
            align, bg, label = "flex-start", "#f59e0b", "YOU (Manual)"
        else:
            align, bg, label = "flex-start", "#334155", "BOT"

        content = content_clean.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        bubbles_html += f"""
        <div style="display:flex;justify-content:{align};margin:8px 0">
            <div style="max-width:70%;background:{bg};color:white;padding:10px 14px;border-radius:12px">
                <div style="font-size:10px;opacity:0.7;margin-bottom:4px">{label} · {msg['timestamp']}</div>
                <div>{content}</div>
            </div>
        </div>
        """

    banner = ""
    if sent == "1":
        banner = '<div style="background:#10b981;color:white;padding:10px;border-radius:6px;margin-bottom:16px">✓ Message sent successfully!</div>'
    elif error:
        err_clean = error.replace("<", "&lt;").replace(">", "&gt;")
        banner = f'<div style="background:#dc2626;color:white;padding:10px;border-radius:6px;margin-bottom:16px">✗ Failed: {err_clean}</div>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Chat with +{sender_id}</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <style>
            body {{ font-family: -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 20px; padding-bottom: 140px; }}
            a {{ color: #a78bfa; text-decoration: none; }}
            h1 {{ margin: 0 0 8px; color: #fff; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            .send-box {{ position: fixed; bottom: 0; left: 0; right: 0; background: #1e293b; padding: 16px; border-top: 1px solid #334155; }}
            .send-form {{ max-width: 800px; margin: 0 auto; display: flex; gap: 8px; }}
            .send-form textarea {{ flex: 1; background: #0f172a; color: #e2e8f0; border: 1px solid #334155; border-radius: 8px; padding: 10px; resize: none; font-family: inherit; font-size: 14px; min-height: 50px; }}
            .send-form button {{ background: #8b5cf6; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: 600; }}
            .send-form button:hover {{ background: #7c3aed; }}
            .send-form button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
            .legend {{ font-size: 11px; color: #64748b; margin-top: 8px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/admin">← Back to all conversations</a>
            <h1>Chat with +{sender_id}</h1>
            <div style="color:#94a3b8;margin-bottom:20px">{len(messages)} total messages</div>
            {banner}
            <div>
                {bubbles_html}
            </div>
        </div>

        <div class="send-box">
            <form class="send-form" method="POST" action="/admin/chat/{sender_id}/send">
                <textarea name="message" placeholder="Type your message... (will be sent as +{sender_id})" required maxlength="4000"></textarea>
                <button type="submit">Send</button>
            </form>
            <div class="legend" style="max-width:800px;margin:8px auto 0">
                💡 Manual messages from you appear in <span style="color:#f59e0b">orange</span>. Bot messages appear in <span style="color:#94a3b8">gray</span>.
            </div>
        </div>

        <script>
            // Auto-scroll to bottom on load
            window.scrollTo(0, document.body.scrollHeight);
            // Allow Ctrl+Enter to submit
            document.querySelector('textarea').addEventListener('keydown', function(e) {{
                if (e.ctrlKey && e.key === 'Enter') {{
                    e.target.form.submit();
                }}
            }});
        </script>
    </body>
    </html>
    """
    return html


@app.post("/admin/chat/{sender_id}/send")
def admin_send_message(sender_id: str, message: str = Form(...), user: str = Depends(verify_admin)):
    """Sends a manual message from admin to a student via WhatsApp."""
    message = message.strip()
    if not message:
        return RedirectResponse(url=f"/admin/chat/{sender_id}?error=Empty+message", status_code=303)

    result = send_whatsapp_message(sender_id, message)

    if result is None:
        return RedirectResponse(
            url=f"/admin/chat/{sender_id}?error=Failed+to+send+(check+logs)",
            status_code=303,
        )

    # Save to DB with [ADMIN] prefix so we can render it differently
    database.save_message(sender_id, "assistant", f"[ADMIN] {message}")

    return RedirectResponse(url=f"/admin/chat/{sender_id}?sent=1", status_code=303)


@app.get("/admin/api/conversations")
def admin_api_conversations(user: str = Depends(verify_admin)):
    """JSON endpoint listing all conversations."""
    return {"conversations": database.get_all_conversations()}
