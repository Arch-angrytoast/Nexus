import asyncio
import os
from discord.ext import commands
import discord

async def test_load():
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)

    # Mock db_conn to satisfy Cog init without needing a real DB config
    class MockDB:
        def cursor(self):
            class MockCursor:
                def execute(self, *args, **kwargs): pass
                def fetchall(self): return []
                def fetchone(self): return None
            return MockCursor()
        def commit(self): pass

    bot.db_conn = MockDB()

    try:
        await bot.load_extension("cogs.core_commands")
        await bot.load_extension("cogs.moderation")
        print("Cogs loaded successfully!")
    except Exception as e:
        print(f"Failed to load cogs: {e}")

asyncio.run(test_load())
