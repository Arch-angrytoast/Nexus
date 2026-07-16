import re

with open('bot.py', 'r') as f:
    content = f.read()

db_setup = """
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel_id INTEGER,
            status TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
"""
content = content.replace("    return conn", db_setup + "    return conn")

with open('bot.py', 'w') as f:
    f.write(content)
