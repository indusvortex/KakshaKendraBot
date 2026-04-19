import sqlite3
from datetime import datetime
from typing import List, Dict

DB_PATH = "whatsapp_bot.db"


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
