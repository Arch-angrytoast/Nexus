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
            key TEXT PRIMARY KEY,
            value TEXT
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
        # Load the core commands cog
        await self.load_extension("cogs.core_commands")
        await self.load_extension("cogs.moderation")
        await self.load_extension("cogs.automod")
        await self.load_extension("cogs.help")
        await self.load_extension("cogs.status")
        await self.load_extension("cogs.antinuke")

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
