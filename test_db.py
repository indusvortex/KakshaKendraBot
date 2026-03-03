import sqlite3

conn = sqlite3.connect('whatsapp_bot.db')
res = conn.execute("SELECT content FROM messages WHERE role='assistant' ORDER BY timestamp DESC LIMIT 5").fetchall()

with open('dummy_test.txt', 'w', encoding='utf-8') as f:
    for row in res:
        f.write("===MESSAGE===\n")
        f.write(row[0] + "\n")
