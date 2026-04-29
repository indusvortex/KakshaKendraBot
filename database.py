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
