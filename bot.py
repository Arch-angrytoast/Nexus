import os
import sqlite3
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("COMMAND_PREFIX", "!")

def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE server_config ADD COLUMN guild_id TEXT DEFAULT '1519633747559841844'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE leveling_rewards ADD COLUMN guild_id TEXT DEFAULT '1519633747559841844'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE leveling_multipliers ADD COLUMN guild_id TEXT DEFAULT '1519633747559841844'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS joke_meters (
            meter_name TEXT PRIMARY KEY,
            emoji TEXT
        )
    ''')
    conn.commit()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS joke_actions (
            action_name TEXT PRIMARY KEY,
            gifs TEXT
        )
    ''')
    conn.commit()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS score_overrides (
            target_id INTEGER,
            meter_name TEXT,
            utc_date TEXT,
            score INTEGER,
            PRIMARY KEY (target_id, meter_name, utc_date)
        )
    ''')
    conn.commit()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            mod_id INTEGER,
            reason TEXT,
            points INTEGER,
            timestamp TEXT
        )
    ''')
    conn.commit()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_config (
            guild_id TEXT,
            key TEXT,
            value TEXT,
            PRIMARY KEY (guild_id, key)
        )
    ''')
    conn.commit()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dashboard_permissions (
            guild_id TEXT,
            role_id TEXT,
            PRIMARY KEY (guild_id, role_id)
        )
    ''')
    conn.commit()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dashboard_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT,
            user_id TEXT,
            user_name TEXT,
            action TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log_config (
            guild_id TEXT PRIMARY KEY,
            message_channel TEXT,
            member_channel TEXT,
            server_channel TEXT,
            voice_channel TEXT
        )
    ''')
    conn.commit()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ticket_panels (
            panel_id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            initial_message TEXT,
            claimed_message TEXT,
            ping_role_id TEXT,
            created_category_id TEXT,
            claimed_category_id TEXT
        )
    ''')
    conn.commit()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel_id INTEGER,
            status TEXT,
            created_at TEXT,
            panel_id TEXT
        )
    ''')
    conn.commit()

    try:
        cursor.execute("ALTER TABLE tickets ADD COLUMN panel_id TEXT DEFAULT 'default'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ticket_buttons (
            button_id INTEGER PRIMARY KEY AUTOINCREMENT,
            panel_id TEXT,
            label TEXT,
            emoji TEXT,
            ping_role_id TEXT,
            category_id TEXT
        )
    ''')
    conn.commit()

    return conn

class NexusBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True
        intents.auto_moderation_configuration = True
        intents.auto_moderation_execution = True
        super().__init__(command_prefix=PREFIX, intents=intents, help_command=None)
        self.db_conn = init_db()

    async def setup_hook(self):
        # Start Quart Web Server in the background loop
        import webserver
        self.loop.create_task(webserver.run_server(self))

        # Load the core commands cog
        await self.load_extension("cogs.core_commands")
        await self.load_extension("cogs.moderation")
        await self.load_extension("cogs.automod")
        await self.load_extension("cogs.help")
        await self.load_extension("cogs.status")
        await self.load_extension("cogs.antinuke")
        await self.load_extension("cogs.tickets")
        await self.load_extension("cogs.utility")
        await self.load_extension("cogs.livestatus")
        await self.load_extension("cogs.changelogs")
        await self.load_extension("cogs.misc")
        await self.load_extension("cogs.leveling")
        await self.load_extension("cogs.auditlog")

        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash commands.")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('Database initialized.')
        print('------')

nexus = NexusBot()

if __name__ == "__main__":
    if TOKEN and TOKEN != "your_token_here":
        nexus.run(TOKEN)
    else:
        print("Please set your DISCORD_TOKEN in the .env file.")
