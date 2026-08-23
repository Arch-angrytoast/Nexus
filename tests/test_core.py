import pytest
import discord.ext.test as dpytest
import discord
from discord.ext import commands
import sys
import os
import asyncio

# Add parent directory to path so we can import the cogs
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot

@pytest.fixture
async def test_bot():
    bot_instance = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await bot_instance._async_setup_hook()

    dpytest.configure(bot_instance)
    return bot_instance

@pytest.mark.asyncio
async def test_ping():
    # Setup test bot
    bot_instance = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await bot_instance.load_extension("cogs.misc")

    dpytest.configure(bot_instance)
    await dpytest.message("!ping")
    assert dpytest.verify().message().contains().content("Pong!")

@pytest.mark.asyncio
async def test_math():
    bot_instance = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await bot_instance.load_extension("cogs.misc")

    dpytest.configure(bot_instance)
    await dpytest.message("!math 5 + 5")
    assert dpytest.verify().message().contains().content("10")

@pytest.mark.asyncio
async def test_leveling_math():
    import cogs.leveling as leveling
    class DummyBot:
        def __init__(self):
            import sqlite3
            self.db_conn = sqlite3.connect(":memory:")

    cog = leveling.Leveling(DummyBot())
    assert cog.calc_xp_for_level(1) == 155
    assert cog.calc_xp_for_level(2) == 220
    assert cog.calc_xp_for_level(10) == 1100

    assert cog.get_level_from_xp(160) == 1
    assert cog.get_level_from_xp(1150) == 10
