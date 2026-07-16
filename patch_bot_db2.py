import re

with open('bot.py', 'r') as f:
    content = f.read()

db_setup = """
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ticket_config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
"""
content = content.replace("    return conn", db_setup + "    return conn")

with open('bot.py', 'w') as f:
    f.write(content)
