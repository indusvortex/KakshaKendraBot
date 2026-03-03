import sqlite3
import json
from datetime import datetime
from typing import List, Dict

DB_PATH = "whatsapp_bot.db"

def init_db():
    """Initializes the SQLite database with the messages table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_message(sender_id: str, role: str, content: str):
    """Saves a message to the database. Role can be 'user' or 'assistant'."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (sender_id, role, content)
        VALUES (?, ?, ?)
    ''', (sender_id, role, content))
    conn.commit()
    conn.close()

def get_recent_messages(sender_id: str, limit: int = 10) -> List[Dict[str, str]]:
    """Retrieves the last `limit` messages for a specific sender_id."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # We fetch the last `limit` messages, ordered by descending ID to get the newest,
    # then reverse them in Python to put them in chronological order.
    cursor.execute('''
        SELECT role, content FROM messages
        WHERE sender_id = ?
        ORDER BY id DESC
        LIMIT ?
    ''', (sender_id, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    # Reverse to chronological order (oldest -> newest in the recent window)
    messages = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
    return messages
