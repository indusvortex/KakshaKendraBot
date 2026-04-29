import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, HTTPException, Response, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv

import database
from utils import (
    generate_ai_response,
    send_whatsapp_message,
    upload_media_to_whatsapp,
    send_whatsapp_media,
)

# India Standard Time = UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))


def to_ist(utc_str: str | None, fmt: str = "%d %b %Y, %I:%M %p") -> str:
    """Converts SQLite-stored UTC timestamp string to IST formatted string."""
    if not utc_str:
        return ""
    try:
        dt_utc = datetime.strptime(utc_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        return dt_utc.astimezone(IST).strftime(fmt)
    except Exception:
        return utc_str

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

                    # Capture contact display name (sent in webhook payload alongside messages)
                    contacts_by_wa_id = {}
                    for contact in value.get("contacts", []):
                        wa_id = contact.get("wa_id")
                        name = contact.get("profile", {}).get("name")
                        if wa_id and name:
                            contacts_by_wa_id[wa_id] = name

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

                            # Save / update the student's display name for the dashboard
                            if sender_id in contacts_by_wa_id:
                                database.upsert_contact(sender_id, contacts_by_wa_id[sender_id])

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

def _initials_avatar(name: str | None, phone: str) -> str:
    """Returns a small HTML <span> with initials or phone digits as a colored avatar."""
    if name and name.strip():
        parts = name.strip().split()
        initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()
    else:
        initials = phone[-2:] if len(phone) >= 2 else phone
    # Hash phone -> color so each student gets a consistent color
    color_palette = ["#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#3b82f6", "#ec4899", "#14b8a6"]
    color = color_palette[sum(ord(c) for c in phone) % len(color_palette)]
    return (
        f'<span style="display:inline-flex;align-items:center;justify-content:center;'
        f'width:36px;height:36px;border-radius:50%;background:{color};color:white;'
        f'font-weight:600;font-size:13px;flex-shrink:0">{initials}</span>'
    )


def _clean_message_text(text: str):
    """
    Strips [OPTIONS]...[/OPTIONS] and [CTA_URL ...] tags from a saved bot message
    so the admin dashboard shows the human-readable body + button chips separately.
    Returns (clean_text, list_of_button_labels).
    """
    import re as _re

    buttons = []

    options_match = _re.search(r'\[OPTIONS\](.*?)\[/OPTIONS\]', text, _re.DOTALL)
    if options_match:
        for line in options_match.group(1).strip().split("\n"):
            line = line.strip()
            if line:
                buttons.append(line)
        text = _re.sub(r'\[OPTIONS\].*?\[/OPTIONS\]', '', text, flags=_re.DOTALL)

    cta_match = _re.search(r'\[CTA_URL\s+display="([^"]+)"\s+url="([^"]+)"\]', text)
    if cta_match:
        buttons.append(f'🔗 {cta_match.group(1)}')
        text = _re.sub(r'\[CTA_URL[^\]]*\]', '', text)

    return text.strip(), buttons


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(user: str = Depends(verify_admin)):
    """Lists all student conversations with last message preview."""
    conversations = database.get_all_conversations()

    rows_html = ""
    unread_count = 0
    if not conversations:
        rows_html = "<tr><td colspan='5' style='text-align:center;padding:40px;color:#888'>No conversations yet. Send 'Hi' to your bot to start!</td></tr>"
    else:
        for c in conversations:
            raw_msg = c["last_message"] or ""
            clean_text, _btns = _clean_message_text(raw_msg)
            preview = clean_text[:80].replace("<", "&lt;").replace(">", "&gt;")
            if len(clean_text) > 80:
                preview += "..."

            role_badge = "BOT" if c["last_role"] == "assistant" else "STUDENT"
            badge_color = "#8b5cf6" if c["last_role"] == "assistant" else "#10b981"

            new_badge = ''
            row_bg = ''
            if c.get("unread"):
                unread_count += 1
                new_badge = '<span style="background:#ef4444;color:white;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;margin-left:8px">NEW</span>'
                row_bg = 'background:#1e293b'

            display_name = c.get("display_name") or ""
            avatar = _initials_avatar(display_name, c["sender_id"])
            name_html = (
                f'<div style="display:flex;align-items:center;gap:10px">'
                f'{avatar}'
                f'<div>'
                f'<div style="font-weight:600">{display_name or "Unknown"}</div>'
                f'<div style="font-size:11px;color:#94a3b8">+{c["sender_id"]}</div>'
                f'</div>'
                f'</div>'
            )

            rows_html += f"""
            <tr onclick="window.location='/admin/chat/{c['sender_id']}'" style="cursor:pointer;{row_bg}">
                <td>{name_html}</td>
                <td><span style="background:{badge_color};color:white;padding:2px 8px;border-radius:4px;font-size:11px">{role_badge}</span>{new_badge}</td>
                <td>{preview}</td>
                <td>{c['message_count']}</td>
                <td style="font-size:12px;color:#94a3b8">{to_ist(c['last_active'])}</td>
            </tr>
            """

    unread_pill = (
        f'&nbsp;·&nbsp;<span style="background:#ef4444;color:white;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:600">{unread_count} unread</span>'
        if unread_count > 0 else ''
    )

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Kaksha Kendra Bot — Admin</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <meta http-equiv="refresh" content="30">
        <style>
            body {{ font-family: -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 20px; }}
            h1 {{ margin: 0 0 20px; color: #fff; }}
            .stats {{ background: #1e293b; padding: 16px; border-radius: 8px; margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; }}
            th {{ background: #334155; padding: 12px; text-align: left; font-size: 12px; text-transform: uppercase; }}
            td {{ padding: 14px 12px; border-top: 1px solid #334155; font-size: 14px; vertical-align: middle; }}
            tr:hover td {{ background: #334155; }}
            .refresh {{ background: #8b5cf6; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; }}
        </style>
    </head>
    <body>
        <h1>🎓 Kaksha Kendra Bot — Admin Dashboard</h1>
        <div class="stats">
            <strong>{len(conversations)} student conversations</strong>{unread_pill}
            &nbsp;·&nbsp;
            <button class="refresh" onclick="location.reload()">↻ Refresh</button>
            <span style="font-size:11px;color:#94a3b8;margin-left:8px">(auto-refreshes every 30s)</span>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Student</th>
                    <th>Status</th>
                    <th>Last Message</th>
                    <th>Total</th>
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

    # Mark this chat as read since admin is viewing it now
    database.mark_chat_read(sender_id)

    # Get display name for the header
    conversations = database.get_all_conversations()
    chat_info = next((c for c in conversations if c["sender_id"] == sender_id), {})
    display_name = chat_info.get("display_name") or "Unknown"

    bubbles_html = ""
    for msg in messages:
        is_user = msg["role"] == "user"
        is_admin_msg = msg["content"].startswith("[ADMIN] ")
        raw = msg["content"][8:] if is_admin_msg else msg["content"]

        if is_user:
            align, bg, label = "flex-end", "#10b981", "STUDENT"
            clean_text, btns = raw, []
        elif is_admin_msg:
            align, bg, label = "flex-start", "#f59e0b", "YOU (Manual)"
            clean_text, btns = raw, []
        else:
            align, bg, label = "flex-start", "#334155", "BOT"
            # Strip [OPTIONS] / [CTA_URL] tags from bot messages and show buttons as chips
            clean_text, btns = _clean_message_text(raw)

        content = clean_text.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")

        buttons_html = ""
        if btns:
            chips = "".join(
                f'<span style="display:inline-block;background:rgba(255,255,255,0.18);padding:3px 10px;border-radius:14px;font-size:11px;margin:3px 4px 0 0">{b[:40].replace("<","&lt;").replace(">","&gt;")}</span>'
                for b in btns
            )
            buttons_html = f'<div style="margin-top:8px;border-top:1px solid rgba(255,255,255,0.15);padding-top:6px">{chips}</div>'

        ts = to_ist(msg['timestamp'], "%d %b, %I:%M %p")
        bubbles_html += f"""
        <div style="display:flex;justify-content:{align};margin:8px 0">
            <div style="max-width:70%;background:{bg};color:white;padding:10px 14px;border-radius:12px">
                <div style="font-size:10px;opacity:0.7;margin-bottom:4px">{label} · {ts} IST</div>
                <div>{content}</div>
                {buttons_html}
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
            body {{ font-family: -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 20px; padding-bottom: 220px; }}
            a {{ color: #a78bfa; text-decoration: none; }}
            h1 {{ margin: 0 0 8px; color: #fff; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            .send-box {{ position: fixed; bottom: 0; left: 0; right: 0; background: #1e293b; padding: 14px 16px; border-top: 1px solid #334155; }}
            .send-form {{ max-width: 800px; margin: 0 auto; display: flex; gap: 10px; align-items: center; }}
            .send-form textarea {{ flex: 1; background: #0f172a; color: #e2e8f0; border: 1px solid #334155; border-radius: 22px; padding: 12px 16px; resize: none; font-family: inherit; font-size: 14px; min-height: 22px; max-height: 120px; line-height: 1.4; }}
            .icon-btn {{ background: #8b5cf6; color: white; border: none; width: 46px; height: 46px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: background 0.15s; }}
            .icon-btn:hover {{ background: #7c3aed; }}
            .icon-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
            .icon-btn svg {{ width: 20px; height: 20px; fill: white; }}
            .legend {{ font-size: 11px; color: #64748b; margin-top: 8px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/admin">← Back to all conversations</a>
            <div style="display:flex;align-items:center;gap:12px;margin:16px 0 4px">
                {_initials_avatar(display_name, sender_id)}
                <div>
                    <h1 style="margin:0;font-size:20px">{display_name}</h1>
                    <div style="color:#94a3b8;font-size:13px">+{sender_id} · {len(messages)} messages</div>
                </div>
            </div>
            <div style="margin:16px 0">{banner}</div>
            <div>
                {bubbles_html}
            </div>
        </div>

        <div class="send-box">
            <form class="send-form" method="POST" action="/admin/chat/{sender_id}/send">
                <textarea name="message" placeholder="Type your message..." required maxlength="4000"></textarea>
                <button type="submit" class="icon-btn" title="Send message" aria-label="Send message">
                    <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                </button>
            </form>

            <form class="media-form" method="POST" action="/admin/chat/{sender_id}/send-media" enctype="multipart/form-data" style="max-width:800px;margin:10px auto 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
                <label style="background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:9px 14px;border-radius:22px;cursor:pointer;font-size:13px;display:inline-flex;align-items:center;gap:6px">
                    📎 <span>Choose file</span>
                    <input type="file" name="file" accept="image/*,video/*,audio/*,application/pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx" required style="display:none" onchange="document.getElementById('file-name').textContent=this.files[0]?.name||''" />
                </label>
                <span id="file-name" style="color:#94a3b8;font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0"></span>
                <input type="text" name="caption" placeholder="Caption (optional)" style="background:#0f172a;color:#e2e8f0;border:1px solid #334155;border-radius:22px;padding:9px 14px;font-size:13px;flex:1;min-width:120px" maxlength="1024" />
                <button type="submit" class="icon-btn" style="background:#10b981" title="Send media" aria-label="Send media">
                    <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                </button>
            </form>

            <div class="legend" style="max-width:800px;margin:8px auto 0">
                💡 Manual messages appear in <span style="color:#f59e0b">orange</span>. Bot messages in <span style="color:#94a3b8">gray</span>. Media up to 100MB.
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


@app.post("/admin/chat/{sender_id}/send-media")
async def admin_send_media(
    sender_id: str,
    file: UploadFile = File(...),
    caption: str = Form(""),
    user: str = Depends(verify_admin),
):
    """Uploads a media file to WhatsApp and sends it to the student."""
    file_bytes = await file.read()
    if not file_bytes:
        return RedirectResponse(url=f"/admin/chat/{sender_id}?error=Empty+file", status_code=303)

    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "file"

    # Determine media type for WhatsApp from MIME
    if mime_type.startswith("image/"):
        media_type = "image"
    elif mime_type.startswith("video/"):
        media_type = "video"
    elif mime_type.startswith("audio/"):
        media_type = "audio"
    else:
        media_type = "document"

    # Step 1: Upload to WhatsApp to get a media ID
    media_id = upload_media_to_whatsapp(file_bytes, filename, mime_type)
    if not media_id:
        return RedirectResponse(
            url=f"/admin/chat/{sender_id}?error=Upload+failed+(check+logs)",
            status_code=303,
        )

    # Step 2: Send the media to the student
    success = send_whatsapp_media(
        sender_id,
        media_id,
        media_type,
        caption=caption.strip() or None,
        filename=filename if media_type == "document" else None,
    )
    if not success:
        return RedirectResponse(
            url=f"/admin/chat/{sender_id}?error=Send+failed+(check+logs)",
            status_code=303,
        )

    # Step 3: Log it in the chat history so admin can see what was sent
    log_message = f"[ADMIN] [Sent {media_type}: {filename}]"
    if caption.strip():
        log_message += f" — {caption.strip()}"
    database.save_message(sender_id, "assistant", log_message)

    return RedirectResponse(url=f"/admin/chat/{sender_id}?sent=1", status_code=303)


@app.get("/admin/api/conversations")
def admin_api_conversations(user: str = Depends(verify_admin)):
    """JSON endpoint listing all conversations."""
    return {"conversations": database.get_all_conversations()}
