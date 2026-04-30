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


# ----------------- Shared CSS for the messenger-style admin -----------------
_ADMIN_CSS = """
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0e1621;
    color: #e6edf3;
    margin: 0;
    overflow: hidden;
}
a { color: #5288c1; text-decoration: none; }

/* Two-pane layout */
.app {
    display: grid;
    grid-template-columns: 360px 1fr;
    height: 100vh;
}

/* === SIDEBAR === */
.sidebar {
    background: #17212b;
    border-right: 1px solid #0b1218;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 4px 0 20px rgba(0,0,0,0.25);
}
.sidebar-header {
    padding: 14px 16px;
    border-bottom: 1px solid #0b1218;
    background: linear-gradient(180deg, #1c2733, #17212b);
}
.sidebar-title { font-size: 18px; font-weight: 700; margin-bottom: 6px; color: #fff; }
.sidebar-meta { font-size: 12px; color: #7d8e9c; }
.unread-pill {
    background: linear-gradient(135deg, #ef4444, #dc2626);
    color: white;
    padding: 2px 9px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
    margin-left: 6px;
    box-shadow: 0 2px 6px rgba(239,68,68,0.4);
}
.search-box {
    padding: 8px 12px;
    border-bottom: 1px solid #0b1218;
}
.search-box input {
    width: 100%;
    background: #242f3d;
    border: none;
    color: #e6edf3;
    padding: 9px 14px;
    border-radius: 18px;
    font-size: 13px;
    outline: none;
    transition: background 0.15s;
}
.search-box input:focus { background: #2b3947; }
.search-box input::placeholder { color: #7d8e9c; }

.chat-list { flex: 1; overflow-y: auto; }
.chat-list::-webkit-scrollbar { width: 6px; }
.chat-list::-webkit-scrollbar-thumb { background: #2b3947; border-radius: 3px; }

.chat-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    cursor: pointer;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    transition: background 0.12s;
    position: relative;
}
.chat-item:hover { background: #202b36; }
.chat-item.active {
    background: linear-gradient(90deg, #2b5278, #1e3d5a);
    box-shadow: inset 3px 0 0 #5288c1;
}
.chat-item .avatar {
    width: 50px;
    height: 50px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 600;
    font-size: 17px;
    flex-shrink: 0;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}
.chat-item .info { flex: 1; min-width: 0; }
.chat-item .name {
    font-weight: 600;
    color: #fff;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 14px;
    display: flex;
    justify-content: space-between;
}
.chat-item .name .time { font-size: 11px; color: #7d8e9c; font-weight: 400; flex-shrink: 0; margin-left: 8px; }
.chat-item .preview {
    font-size: 13px;
    color: #95a3b1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-top: 2px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.chat-item.active .preview, .chat-item.active .name { color: #fff; }
.chat-item .new-dot {
    background: #5288c1;
    color: white;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(82,136,193,0.5);
}

/* === MAIN PANEL === */
.main {
    display: flex;
    flex-direction: column;
    background: #0e1621;
    background-image:
        radial-gradient(circle at 20% 30%, rgba(82,136,193,0.05) 0%, transparent 40%),
        radial-gradient(circle at 80% 70%, rgba(82,136,193,0.04) 0%, transparent 40%);
    overflow: hidden;
}
.main-header {
    padding: 12px 20px;
    border-bottom: 1px solid #0b1218;
    background: #17212b;
    display: flex;
    align-items: center;
    gap: 12px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.25);
    z-index: 10;
}
.main-header .avatar {
    width: 42px;
    height: 42px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 600;
    font-size: 14px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}
.main-header .name { font-weight: 600; font-size: 15px; color: #fff; }
.main-header .sub { font-size: 12px; color: #7d8e9c; }

.messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px 24px;
    display: flex;
    flex-direction: column;
    gap: 4px;
}
.messages::-webkit-scrollbar { width: 6px; }
.messages::-webkit-scrollbar-thumb { background: #2b3947; border-radius: 3px; }

.bubble-row { display: flex; margin: 2px 0; }
.bubble-row.right { justify-content: flex-end; }
.bubble {
    max-width: 65%;
    padding: 8px 12px 6px;
    border-radius: 14px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2);
    line-height: 1.4;
    word-wrap: break-word;
    position: relative;
    transition: transform 0.15s;
}
.bubble:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.35); }
.bubble.student {
    background: linear-gradient(135deg, #2b5278, #1e3d5a);
    color: #fff;
    border-bottom-right-radius: 4px;
}
.bubble.bot {
    background: linear-gradient(135deg, #182533, #1c2b3a);
    color: #e6edf3;
    border-bottom-left-radius: 4px;
}
.bubble.admin {
    background: linear-gradient(135deg, #d97706, #b45309);
    color: #fff;
    border-bottom-left-radius: 4px;
}
.bubble .meta { font-size: 10px; opacity: 0.7; margin-bottom: 3px; font-weight: 600; }
.bubble .content { font-size: 14px; }
.bubble .time {
    font-size: 10px;
    opacity: 0.7;
    margin-top: 4px;
    text-align: right;
}
.bubble .chips {
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px solid rgba(255,255,255,0.15);
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}
.bubble .chip {
    background: rgba(255,255,255,0.15);
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 11px;
}

/* === COMPOSER === */
.composer {
    background: #17212b;
    padding: 12px 20px;
    border-top: 1px solid #0b1218;
    box-shadow: 0 -2px 12px rgba(0,0,0,0.25);
}
.composer-form {
    display: flex;
    align-items: center;
    gap: 10px;
    position: relative;
}
.composer textarea {
    flex: 1;
    background: #242f3d;
    border: none;
    color: #e6edf3;
    padding: 11px 18px;
    border-radius: 22px;
    font-family: inherit;
    font-size: 14px;
    resize: none;
    min-height: 22px;
    max-height: 120px;
    line-height: 1.4;
    outline: none;
    transition: background 0.15s;
}
.composer textarea:focus { background: #2b3947; }
.composer textarea::placeholder { color: #7d8e9c; }

.icon-btn {
    background: #5288c1;
    color: white;
    border: none;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: transform 0.15s, background 0.15s, box-shadow 0.15s;
    box-shadow: 0 2px 6px rgba(82,136,193,0.4);
}
.icon-btn:hover { background: #6699d2; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(82,136,193,0.55); }
.icon-btn:active { transform: translateY(0); }
.icon-btn svg { width: 20px; height: 20px; fill: white; }
.icon-btn.attach { background: transparent; box-shadow: none; color: #7d8e9c; }
.icon-btn.attach:hover { background: #242f3d; color: #5288c1; transform: none; box-shadow: none; }
.icon-btn.attach svg { fill: currentColor; }

/* Attach popup menu */
.attach-menu {
    position: absolute;
    bottom: 56px;
    left: 0;
    background: #1c2b3a;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 6px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.5);
    display: none;
    flex-direction: column;
    gap: 2px;
    z-index: 20;
    min-width: 180px;
}
.attach-menu.open { display: flex; }
.attach-menu button {
    background: none;
    border: none;
    color: #e6edf3;
    padding: 10px 14px;
    text-align: left;
    cursor: pointer;
    border-radius: 8px;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 10px;
    transition: background 0.12s;
}
.attach-menu button:hover { background: #2b3947; }
.attach-menu .icon { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; }

/* Banners */
.banner {
    margin: 12px 20px 0;
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 13px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.3);
}
.banner.success { background: linear-gradient(135deg, #10b981, #059669); color: #fff; }
.banner.error { background: linear-gradient(135deg, #dc2626, #991b1b); color: #fff; }

/* Empty state when no chat selected */
.empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #7d8e9c;
    text-align: center;
}
.empty-state .big-icon {
    font-size: 64px;
    margin-bottom: 16px;
    opacity: 0.4;
}

/* Responsive — stack on mobile */
@media (max-width: 800px) {
    .app { grid-template-columns: 1fr; }
    .sidebar { display: var(--sidebar-display, flex); }
    .main { display: var(--main-display, none); }
    body.chat-open { --sidebar-display: none; --main-display: flex; }
}
"""


def _avatar_html(name: str | None, phone: str, size: int = 50) -> str:
    """Renders a colored circular avatar with initials."""
    if name and name.strip():
        parts = name.strip().split()
        initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()
    else:
        initials = phone[-2:] if len(phone) >= 2 else phone
    palette = ["#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#3b82f6", "#ec4899", "#14b8a6"]
    color = palette[sum(ord(c) for c in phone) % len(palette)]
    color2 = palette[(sum(ord(c) for c in phone) + 3) % len(palette)]
    return (
        f'<div class="avatar" style="width:{size}px;height:{size}px;background:linear-gradient(135deg,{color},{color2})">'
        f'{initials}</div>'
    )


def _render_chat_panel(sender_id: str, sent: str, error: str) -> str:
    """Renders the right-hand chat panel for a selected conversation."""
    if not sender_id:
        return """
        <div class="empty-state">
            <div class="big-icon">💬</div>
            <h2 style="margin:0;color:#e6edf3">Select a chat to start messaging</h2>
            <div style="margin-top:8px;font-size:13px">Pick a student from the sidebar to view the conversation.</div>
        </div>
        """

    # Mark as read since admin is now viewing this chat
    database.mark_chat_read(sender_id)

    messages = database.get_full_conversation(sender_id)
    conversations = database.get_all_conversations()
    chat_info = next((c for c in conversations if c["sender_id"] == sender_id), {})
    display_name = chat_info.get("display_name") or "Unknown"

    bubbles = []
    for msg in messages:
        is_user = msg["role"] == "user"
        is_admin_msg = msg["content"].startswith("[ADMIN] ")
        raw = msg["content"][8:] if is_admin_msg else msg["content"]

        if is_user:
            row_class, bubble_class, label = "right", "student", "Student"
            clean_text, btns = raw, []
        elif is_admin_msg:
            row_class, bubble_class, label = "", "admin", "You (manual)"
            clean_text, btns = raw, []
        else:
            row_class, bubble_class, label = "", "bot", "Bot"
            clean_text, btns = _clean_message_text(raw)

        content = clean_text.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        chips_html = ""
        if btns:
            chips_html = '<div class="chips">' + "".join(
                f'<span class="chip">{b[:40].replace("<","&lt;").replace(">","&gt;")}</span>'
                for b in btns
            ) + "</div>"

        ts = to_ist(msg['timestamp'], "%d %b · %I:%M %p")
        bubbles.append(f"""
        <div class="bubble-row {row_class}">
            <div class="bubble {bubble_class}">
                <div class="meta">{label}</div>
                <div class="content">{content}</div>
                {chips_html}
                <div class="time">{ts}</div>
            </div>
        </div>
        """)

    bubbles_html = "".join(bubbles) or '<div style="text-align:center;color:#7d8e9c;padding:40px">No messages yet.</div>'

    banner = ""
    if sent == "1":
        banner = '<div class="banner success">✓ Message sent successfully</div>'
    elif error:
        err_clean = error.replace("<", "&lt;").replace(">", "&gt;")
        banner = f'<div class="banner error">✗ {err_clean}</div>'

    return f"""
    <div class="main-header">
        <a href="/admin" style="color:#7d8e9c;text-decoration:none;font-size:18px;display:none" class="back-btn" onclick="document.body.classList.remove('chat-open');return false">←</a>
        {_avatar_html(display_name, sender_id, 42)}
        <div style="flex:1">
            <div class="name">{display_name}</div>
            <div class="sub">+{sender_id} · {len(messages)} messages</div>
        </div>
    </div>
    {banner}
    <div class="messages" id="messages">
        {bubbles_html}
    </div>
    <div class="composer">
        <form class="composer-form" method="POST" action="/admin/chat/{sender_id}/send" id="text-form">
            <button type="button" class="icon-btn attach" id="attach-toggle" title="Attach" aria-label="Attach">
                <svg viewBox="0 0 24 24"><path d="M16.5 6.5v10.5a4.5 4.5 0 1 1-9 0V5a3 3 0 1 1 6 0v11.5a1.5 1.5 0 1 1-3 0V6h-1.5v10.5a3 3 0 1 0 6 0V5a4.5 4.5 0 1 0-9 0v12a6 6 0 1 0 12 0V6.5z"/></svg>
            </button>
            <div class="attach-menu" id="attach-menu">
                <button type="button" onclick="pickFile('image/*')"><span class="icon" style="background:#3b82f6">🖼️</span> Photo</button>
                <button type="button" onclick="pickFile('video/*')"><span class="icon" style="background:#ef4444">🎬</span> Video</button>
                <button type="button" onclick="pickFile('audio/*')"><span class="icon" style="background:#10b981">🎵</span> Audio</button>
                <button type="button" onclick="pickFile('application/pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt')"><span class="icon" style="background:#f59e0b">📄</span> Document</button>
            </div>
            <textarea name="message" placeholder="Message..." required maxlength="4000" id="msg-input"></textarea>
            <button type="submit" class="icon-btn" title="Send" aria-label="Send">
                <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
            </button>
        </form>
        <form id="media-form" method="POST" action="/admin/chat/{sender_id}/send-media" enctype="multipart/form-data" style="display:none">
            <input type="file" name="file" id="media-file" />
            <input type="hidden" name="caption" id="media-caption" />
        </form>
    </div>
    """


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    chat: str = "",
    sent: str = "",
    error: str = "",
    user: str = Depends(verify_admin),
):
    """Telegram-style dashboard: sidebar with conversations + main chat panel."""
    conversations = database.get_all_conversations()
    unread_count = sum(1 for c in conversations if c.get("unread"))

    # Sidebar items
    items = []
    for c in conversations:
        is_active = c["sender_id"] == chat
        raw_msg = c["last_message"] or ""
        clean_text, _btns = _clean_message_text(raw_msg)
        preview = clean_text[:50].replace("<", "&lt;").replace(">", "&gt;")
        if len(clean_text) > 50:
            preview += "…"
        prefix = "🤖 " if c["last_role"] == "assistant" else ""
        if c["last_role"] == "assistant" and raw_msg.startswith("[ADMIN] "):
            prefix = "✓ "

        time_str = to_ist(c["last_active"], "%I:%M %p")
        new_dot = f'<span class="new-dot">{"" if c.get("unread") else ""}{"!" if c.get("unread") else ""}</span>' if c.get("unread") else ''

        display_name = c.get("display_name") or "Unknown"
        items.append(f"""
        <div class="chat-item {'active' if is_active else ''}" onclick="window.location='/admin?chat={c['sender_id']}'" data-search="{display_name.lower()} {c['sender_id']}">
            {_avatar_html(display_name, c['sender_id'], 50)}
            <div class="info">
                <div class="name"><span>{display_name}</span><span class="time">{time_str}</span></div>
                <div class="preview"><span style="overflow:hidden;text-overflow:ellipsis">{prefix}{preview}</span>{new_dot}</div>
            </div>
        </div>
        """)

    items_html = "".join(items) or '<div style="text-align:center;padding:40px;color:#7d8e9c">No conversations yet.</div>'
    unread_html = f'<span class="unread-pill">{unread_count} new</span>' if unread_count > 0 else ''

    chat_panel = _render_chat_panel(chat, sent, error)

    body_class = "chat-open" if chat else ""

    # Build page title
    title = "Kaksha Kendra Bot"
    if chat:
        matched = next((c for c in conversations if c["sender_id"] == chat), None)
        if matched:
            title += " · " + (matched.get("display_name") or f"+{chat}")

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <meta http-equiv="refresh" content="60">
        <style>{_ADMIN_CSS}</style>
    </head>
    <body class="{body_class}">
        <div class="app">
            <aside class="sidebar">
                <div class="sidebar-header">
                    <div class="sidebar-title">🎓 Kaksha Kendra Bot {unread_html}</div>
                    <div class="sidebar-meta">{len(conversations)} chats · auto-refresh 60s</div>
                </div>
                <div class="search-box">
                    <input type="text" id="search" placeholder="🔍 Search students..." oninput="filterChats(this.value)" />
                </div>
                <div class="chat-list" id="chat-list">
                    {items_html}
                </div>
            </aside>
            <main class="main">
                {chat_panel}
            </main>
        </div>

        <script>
            // Live-filter sidebar
            function filterChats(q) {{
                q = q.toLowerCase().trim();
                document.querySelectorAll('.chat-item').forEach(el => {{
                    const search = el.dataset.search || '';
                    el.style.display = (!q || search.includes(q)) ? '' : 'none';
                }});
            }}

            // Auto-scroll messages to bottom
            const msgs = document.getElementById('messages');
            if (msgs) msgs.scrollTop = msgs.scrollHeight;

            // Attach menu toggle
            const attachToggle = document.getElementById('attach-toggle');
            const attachMenu = document.getElementById('attach-menu');
            if (attachToggle) {{
                attachToggle.addEventListener('click', e => {{
                    e.stopPropagation();
                    attachMenu.classList.toggle('open');
                }});
                document.addEventListener('click', () => attachMenu?.classList.remove('open'));
            }}

            // File picker -> send via media form
            window.pickFile = function(accept) {{
                const f = document.getElementById('media-file');
                f.accept = accept;
                f.onchange = function() {{
                    if (this.files[0]) {{
                        const cap = prompt('Caption (optional):', '');
                        document.getElementById('media-caption').value = cap || '';
                        document.getElementById('media-form').submit();
                    }}
                }};
                f.click();
                attachMenu.classList.remove('open');
            }};

            // Ctrl+Enter to send
            const msgInput = document.getElementById('msg-input');
            if (msgInput) {{
                msgInput.focus();
                msgInput.addEventListener('keydown', function(e) {{
                    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {{
                        e.target.form.submit();
                    }}
                }});
            }}
        </script>
    </body>
    </html>
    """


@app.get("/admin/chat/{sender_id}", response_class=HTMLResponse)
def admin_chat_view_redirect(sender_id: str, sent: str = "", error: str = "", user: str = Depends(verify_admin)):
    """Backwards-compat: redirect old chat URLs to new query-string format."""
    qs = f"?chat={sender_id}"
    if sent:
        qs += f"&sent={sent}"
    if error:
        qs += f"&error={error}"
    return RedirectResponse(url=f"/admin{qs}", status_code=303)


@app.post("/admin/chat/{sender_id}/send")
def admin_send_message(sender_id: str, message: str = Form(...), user: str = Depends(verify_admin)):
    """Sends a manual message from admin to a student via WhatsApp."""
    message = message.strip()
    if not message:
        return RedirectResponse(url=f"/admin?chat={sender_id}&error=Empty+message", status_code=303)

    result = send_whatsapp_message(sender_id, message)

    if result is None:
        return RedirectResponse(
            url=f"/admin?chat={sender_id}&error=Failed+to+send+(check+logs)",
            status_code=303,
        )

    # Save to DB with [ADMIN] prefix so we can render it differently
    database.save_message(sender_id, "assistant", f"[ADMIN] {message}")

    return RedirectResponse(url=f"/admin?chat={sender_id}&sent=1", status_code=303)


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
        return RedirectResponse(url=f"/admin?chat={sender_id}&error=Empty+file", status_code=303)

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
            url=f"/admin?chat={sender_id}&error=Upload+failed+(check+logs)",
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
            url=f"/admin?chat={sender_id}&error=Send+failed+(check+logs)",
            status_code=303,
        )

    # Step 3: Log it in the chat history so admin can see what was sent
    log_message = f"[ADMIN] [Sent {media_type}: {filename}]"
    if caption.strip():
        log_message += f" — {caption.strip()}"
    database.save_message(sender_id, "assistant", log_message)

    return RedirectResponse(url=f"/admin?chat={sender_id}&sent=1", status_code=303)


@app.get("/admin/api/conversations")
def admin_api_conversations(user: str = Depends(verify_admin)):
    """JSON endpoint listing all conversations."""
    return {"conversations": database.get_all_conversations()}
