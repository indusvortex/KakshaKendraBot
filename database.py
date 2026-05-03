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
    """Initializes the SQLite database with the messages and chats tables."""
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
        conn.commit()


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
    """Deletes all messages and contact info for a sender. Returns rows deleted."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute('DELETE FROM messages WHERE sender_id = ?', (sender_id,))
        deleted = cur.rowcount
        conn.execute('DELETE FROM chats WHERE sender_id = ?', (sender_id,))
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
