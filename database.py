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
    """Initializes the SQLite database with the messages table."""
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
    Returns a list of all unique senders with their last message and total count.
    Sorted by most recent activity.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''
            SELECT
                sender_id,
                COUNT(*) as message_count,
                MAX(timestamp) as last_active,
                (SELECT content FROM messages m2
                 WHERE m2.sender_id = m1.sender_id
                 ORDER BY id DESC LIMIT 1) as last_message,
                (SELECT role FROM messages m3
                 WHERE m3.sender_id = m1.sender_id
                 ORDER BY id DESC LIMIT 1) as last_role
            FROM messages m1
            GROUP BY sender_id
            ORDER BY last_active DESC
            '''
        ).fetchall()
    return [dict(row) for row in rows]


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
