import os
import sqlite3
from pathlib import Path
from typing import List, Dict

# Use a persistent path if DATABASE_PATH env var is set (e.g. /data/whatsapp_bot.db on Railway Volume).
# Falls back to local file for development.
DB_PATH = os.getenv("DATABASE_PATH", "whatsapp_bot.db")

# Make sure the parent directory exists when DB_PATH points to a mounted volume
_db_dir = Path(DB_PATH).parent
if str(_db_dir) and str(_db_dir) != ".":
    _db_dir.mkdir(parents=True, exist_ok=True)


def init_db():
    """Initializes the SQLite database with the messages, chats, and push_subs tables."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id TEXT    NOT NULL,
                role      TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                sender_id    TEXT PRIMARY KEY,
                display_name TEXT,
                last_read_at DATETIME
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS push_subs (
                endpoint   TEXT PRIMARY KEY,
                p256dh     TEXT NOT NULL,
                auth       TEXT NOT NULL,
                role       TEXT DEFAULT 'super_admin',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Add role column to existing push_subs tables (safe ALTER)
        try:
            conn.execute("ALTER TABLE push_subs ADD COLUMN role TEXT DEFAULT 'super_admin'")
        except sqlite3.OperationalError:
            pass  # Column already exists

        conn.execute('''
            CREATE TABLE IF NOT EXISTS lead_reminders (
                sender_id          TEXT PRIMARY KEY,
                status             TEXT DEFAULT 'pending',
                naam               TEXT,
                class_label        TEXT,
                phone              TEXT,
                source             TEXT,
                next_call          TEXT,
                notes              TEXT,
                created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_reminded_at   DATETIME,
                admin_notified_at  DATETIME,
                called_at          DATETIME
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS app_state (
                key        TEXT PRIMARY KEY,
                value      TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()


# ============================================================
# Generic key/value app state — used for team login/logout, etc.
# ============================================================

def set_state(key: str, value: str):
    """Persists a key/value pair."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            INSERT INTO app_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=CURRENT_TIMESTAMP
            ''',
            (key, value),
        )
        conn.commit()


def get_state(key: str, default: str | None = None) -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT value FROM app_state WHERE key = ?", (key,)
        ).fetchone()
    return row[0] if row else default


def count_leads_since(utc_iso: str | None) -> int:
    """
    Counts how many leads arrived (got a lead_reminders row created)
    AFTER the given UTC ISO timestamp. Used to tell the team how many
    new leads piled up while they were logged out.
    Returns 0 if utc_iso is None or unparseable.
    """
    if not utc_iso:
        return 0
    # Normalize ISO to SQLite-friendly 'YYYY-MM-DD HH:MM:SS' (UTC)
    try:
        ts = utc_iso.replace("T", " ").split(".")[0].replace("Z", "")
    except Exception:
        return 0
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM lead_reminders WHERE created_at >= ?",
            (ts,),
        ).fetchone()
    return row[0] if row else 0


def get_call_stats() -> Dict:
    """Returns counts for the team summary: calls yesterday/today + pending."""
    with sqlite3.connect(DB_PATH) as conn:
        called_yesterday = conn.execute(
            """
            SELECT COUNT(*) FROM lead_reminders
            WHERE status = 'called'
            AND date(called_at) = date('now', '-1 day')
            """
        ).fetchone()[0]

        called_today = conn.execute(
            """
            SELECT COUNT(*) FROM lead_reminders
            WHERE status = 'called'
            AND date(called_at) = date('now')
            """
        ).fetchone()[0]

        pending_now = conn.execute(
            "SELECT COUNT(*) FROM lead_reminders WHERE status = 'pending'"
        ).fetchone()[0]

        new_today = conn.execute(
            """
            SELECT COUNT(*) FROM lead_reminders
            WHERE date(created_at) = date('now')
            """
        ).fetchone()[0]

    return {
        "called_yesterday": called_yesterday,
        "called_today": called_today,
        "pending_now": pending_now,
        "new_today": new_today,
    }


def add_push_subscription(endpoint: str, p256dh: str, auth: str, role: str = "super_admin"):
    """Saves (or replaces) a browser's push subscription, tagged with the user's role."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            INSERT INTO push_subs (endpoint, p256dh, auth, role)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET
                p256dh=excluded.p256dh,
                auth=excluded.auth,
                role=excluded.role
            ''',
            (endpoint, p256dh, auth, role),
        )
        conn.commit()


def remove_push_subscription(endpoint: str):
    """Deletes a subscription (e.g. browser unsubscribed or 410 Gone)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('DELETE FROM push_subs WHERE endpoint = ?', (endpoint,))
        conn.commit()


def get_push_subscriptions(role: str | None = None) -> List[Dict]:
    """
    Returns push subscriptions. If role is given, only returns subs for that role.
    role values: 'super_admin', 'team', or None (all).
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if role:
            rows = conn.execute(
                "SELECT endpoint, p256dh, auth, role FROM push_subs WHERE role = ?",
                (role,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT endpoint, p256dh, auth, role FROM push_subs"
            ).fetchall()
    return [dict(r) for r in rows]


def get_all_push_subscriptions() -> List[Dict]:
    """Backwards-compat: returns every saved push subscription."""
    return get_push_subscriptions(None)


# ============================================================
# Lead Reminders
# ============================================================

def add_lead_reminder(
    sender_id: str,
    naam: str,
    class_label: str,
    phone: str,
    source: str,
):
    """
    Creates a pending-call reminder for a new lead.
    If a reminder already exists for this sender:
      - If status is already 'pending': leaves it alone (no double-create)
      - If status is 'called'/'dismissed': RE-OPENS it as 'pending' so the
        team gets re-alerted (student is messaging again — fresh interest)
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            INSERT INTO lead_reminders
                (sender_id, status, naam, class_label, phone, source, created_at,
                 last_reminded_at, admin_notified_at, called_at)
            VALUES (?, 'pending', ?, ?, ?, ?, CURRENT_TIMESTAMP, NULL, NULL, NULL)
            ON CONFLICT(sender_id) DO UPDATE SET
                status            = CASE
                                      WHEN lead_reminders.status = 'pending'
                                      THEN lead_reminders.status
                                      ELSE 'pending'
                                    END,
                naam              = excluded.naam,
                class_label       = excluded.class_label,
                phone             = excluded.phone,
                source            = excluded.source,
                created_at        = CASE
                                      WHEN lead_reminders.status = 'pending'
                                      THEN lead_reminders.created_at
                                      ELSE CURRENT_TIMESTAMP
                                    END,
                last_reminded_at  = CASE
                                      WHEN lead_reminders.status = 'pending'
                                      THEN lead_reminders.last_reminded_at
                                      ELSE NULL
                                    END,
                admin_notified_at = CASE
                                      WHEN lead_reminders.status = 'pending'
                                      THEN lead_reminders.admin_notified_at
                                      ELSE NULL
                                    END,
                called_at         = CASE
                                      WHEN lead_reminders.status = 'pending'
                                      THEN lead_reminders.called_at
                                      ELSE NULL
                                    END
            ''',
            (sender_id, naam, class_label, phone, source),
        )
        conn.commit()


def get_pending_lead_reminders() -> List[Dict]:
    """Returns all leads with status='pending' (still waiting for someone to call)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT * FROM lead_reminders
            WHERE status = 'pending'
            ORDER BY created_at DESC
            '''
        ).fetchall()
    return [dict(r) for r in rows]


def mark_lead_reminded(sender_id: str):
    """Updates the last_reminded_at timestamp."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE lead_reminders SET last_reminded_at = CURRENT_TIMESTAMP WHERE sender_id = ?",
            (sender_id,),
        )
        conn.commit()


def mark_lead_admin_notified(sender_id: str):
    """Sets admin_notified_at — used so we only escalate once."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE lead_reminders SET admin_notified_at = CURRENT_TIMESTAMP WHERE sender_id = ?",
            (sender_id,),
        )
        conn.commit()


def mark_lead_called(
    sender_id: str,
    naam: str | None = None,
    class_label: str | None = None,
    phone: str | None = None,
    next_call: str | None = None,
    notes: str | None = None,
    status: str = "called",
):
    """Closes a lead reminder when the team confirms they called."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            UPDATE lead_reminders SET
                status = ?,
                naam = COALESCE(?, naam),
                class_label = COALESCE(?, class_label),
                phone = COALESCE(?, phone),
                next_call = COALESCE(?, next_call),
                notes = COALESCE(?, notes),
                called_at = CURRENT_TIMESTAMP
            WHERE sender_id = ?
            ''',
            (status, naam, class_label, phone, next_call, notes, sender_id),
        )
        conn.commit()


def get_lead_reminder(sender_id: str) -> Dict | None:
    """Returns one lead reminder."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM lead_reminders WHERE sender_id = ?",
            (sender_id,),
        ).fetchone()
    return dict(row) if row else None


def upsert_contact(sender_id: str, display_name: str | None):
    """Creates or updates a contact's display name."""
    if not display_name:
        return
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            INSERT INTO chats (sender_id, display_name)
            VALUES (?, ?)
            ON CONFLICT(sender_id) DO UPDATE SET display_name=excluded.display_name
            ''',
            (sender_id, display_name),
        )
        conn.commit()


def mark_chat_read(sender_id: str):
    """Marks all messages in a chat as read by storing the current timestamp."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            INSERT INTO chats (sender_id, last_read_at)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT(sender_id) DO UPDATE SET last_read_at=CURRENT_TIMESTAMP
            ''',
            (sender_id,),
        )
        conn.commit()


def save_message(sender_id: str, role: str, content: str):
    """Saves a message to the database. Role must be 'user' or 'assistant'."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            'INSERT INTO messages (sender_id, role, content) VALUES (?, ?, ?)',
            (sender_id, role, content),
        )
        conn.commit()


def get_recent_messages(sender_id: str, limit: int = 10) -> List[Dict[str, str]]:
    """
    Retrieves the last `limit` messages for a specific sender_id,
    returned in chronological order (oldest first).
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT role, content FROM messages
            WHERE sender_id = ?
            ORDER BY id DESC
            LIMIT ?
            ''',
            (sender_id, limit),
        ).fetchall()

    # Reverse so the list is oldest → newest
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def get_all_conversations() -> List[Dict]:
    """
    Returns all unique senders with last message, message count, display name,
    and whether they have unread messages from the student.
    Sorted by most recent activity.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT
                m1.sender_id,
                COUNT(*) as message_count,
                MAX(m1.timestamp) as last_active,
                (SELECT content FROM messages m2
                 WHERE m2.sender_id = m1.sender_id
                 ORDER BY id DESC LIMIT 1) as last_message,
                (SELECT role FROM messages m3
                 WHERE m3.sender_id = m1.sender_id
                 ORDER BY id DESC LIMIT 1) as last_role,
                c.display_name,
                c.last_read_at,
                (SELECT MAX(timestamp) FROM messages m4
                 WHERE m4.sender_id = m1.sender_id AND m4.role = 'user') as last_user_msg_at
            FROM messages m1
            LEFT JOIN chats c ON c.sender_id = m1.sender_id
            GROUP BY m1.sender_id
            ORDER BY last_active DESC
            '''
        ).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        # Mark as unread if last user message is newer than last_read_at (or never read)
        d["unread"] = bool(
            d["last_user_msg_at"]
            and (not d["last_read_at"] or d["last_user_msg_at"] > d["last_read_at"])
        )
        result.append(d)
    return result


def get_full_conversation(sender_id: str) -> List[Dict]:
    """Returns ALL messages for a given sender, oldest first."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT role, content, timestamp
            FROM messages
            WHERE sender_id = ?
            ORDER BY id ASC
            ''',
            (sender_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_chat(sender_id: str) -> int:
    """Deletes all messages, contact info, AND any lead reminder for a sender.
    Returns the number of message rows deleted."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute('DELETE FROM messages WHERE sender_id = ?', (sender_id,))
        deleted = cur.rowcount
        conn.execute('DELETE FROM chats WHERE sender_id = ?', (sender_id,))
        conn.execute('DELETE FROM lead_reminders WHERE sender_id = ?', (sender_id,))
        conn.commit()
    return deleted


def get_all_messages_with_contact() -> List[Dict]:
    """
    Returns every message in the database joined with the contact's display name.
    Ordered chronologically (oldest first). Used for CSV/Excel export.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT
                m.id,
                m.sender_id,
                COALESCE(c.display_name, '') AS display_name,
                m.role,
                m.content,
                m.timestamp
            FROM messages m
            LEFT JOIN chats c ON c.sender_id = m.sender_id
            ORDER BY m.id ASC
            '''
        ).fetchall()
    return [dict(row) for row in rows]


def get_stats() -> Dict:
    """
    Returns aggregate statistics about messages and students:
    counts for today, last 7 days, all-time, plus DB size.
    """
    stats = {}
    with sqlite3.connect(DB_PATH) as conn:
        # All-time totals
        stats["total_messages"] = conn.execute(
            "SELECT COUNT(*) FROM messages"
        ).fetchone()[0]
        stats["total_students"] = conn.execute(
            "SELECT COUNT(DISTINCT sender_id) FROM messages"
        ).fetchone()[0]
        stats["total_user_messages"] = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE role = 'user'"
        ).fetchone()[0]
        stats["total_bot_replies"] = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE role = 'assistant'"
        ).fetchone()[0]

        # Last 24 hours
        stats["messages_today"] = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE timestamp >= datetime('now', '-1 day')"
        ).fetchone()[0]
        stats["new_students_today"] = conn.execute(
            """
            SELECT COUNT(DISTINCT sender_id) FROM messages
            WHERE sender_id NOT IN (
                SELECT DISTINCT sender_id FROM messages
                WHERE timestamp < datetime('now', '-1 day')
            )
            AND timestamp >= datetime('now', '-1 day')
            """
        ).fetchone()[0]

        # Last 7 days
        stats["messages_week"] = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE timestamp >= datetime('now', '-7 days')"
        ).fetchone()[0]
        stats["active_students_week"] = conn.execute(
            "SELECT COUNT(DISTINCT sender_id) FROM messages WHERE timestamp >= datetime('now', '-7 days')"
        ).fetchone()[0]

    # Database file size on disk
    try:
        stats["db_size_bytes"] = os.path.getsize(DB_PATH)
    except OSError:
        stats["db_size_bytes"] = 0

    return stats
