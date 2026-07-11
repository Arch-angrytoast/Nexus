import os
from datetime import datetime, timezone
import sqlite3
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

import json
import ui_overrides
import snark_pool
import giphy_api
import embed_formatter

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("COMMAND_PREFIX", "!")

intents = discord.Intents.default()
intents.message_content = True

nexus = commands.Bot(command_prefix=PREFIX, intents=intents)

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
    return conn

nexus.db_conn = init_db()

@nexus.event
async def on_ready():
    print(f'Logged in as {nexus.user} (ID: {nexus.user.id})')
    print('Database initialized.')
    print('------')
    try:
        synced = await nexus.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@nexus.tree.command(name="add-meter", description="Add a new joke meter")
@app_commands.describe(name="The trigger word for the meter", emoji="The emoji icon for the meter")
@app_commands.default_permissions(administrator=True)
async def add_meter(interaction: discord.Interaction, name: str, emoji: str):
    meter_name_lower = name.lower()
    try:
        cursor = nexus.db_conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO joke_meters (meter_name, emoji) VALUES (?, ?)", (meter_name_lower, emoji))
        nexus.db_conn.commit()
        await interaction.response.send_message(f"Successfully added/updated meter `{meter_name_lower}` with emoji {emoji}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to add meter: {e}", ephemeral=True)

@nexus.tree.command(name="remove-meter", description="Remove a joke meter")
@app_commands.describe(name="The trigger word of the meter to remove")
@app_commands.default_permissions(administrator=True)
async def remove_meter(interaction: discord.Interaction, name: str):
    meter_name_lower = name.lower()
    try:
        cursor = nexus.db_conn.cursor()
        cursor.execute("DELETE FROM joke_meters WHERE meter_name = ?", (meter_name_lower,))
        if cursor.rowcount > 0:
            nexus.db_conn.commit()
            await interaction.response.send_message(f"Successfully removed meter `{meter_name_lower}`", ephemeral=True)
        else:
            await interaction.response.send_message(f"Meter `{meter_name_lower}` not found.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to remove meter: {e}", ephemeral=True)

import random

async def process_action(author: discord.Member | discord.User, target: discord.Member | discord.User, action_name_raw: str, respond_func) -> bool:
    action_name = action_name_raw.lower()
    cursor = nexus.db_conn.cursor()
    cursor.execute("SELECT gifs FROM joke_actions WHERE action_name = ?", (action_name,))
    row = cursor.fetchone()

    if not row:
        return False # Was not an action

    # Bot immunity Check
    if target.id == nexus.user.id:
        embed = discord.Embed(
            description=random.choice(snark_pool.BOT_IMMUNITY_REPLIES),
            color=discord.Color.from_str("#2B2D31")
        )
        await respond_func(content=f"<@{author.id}>", embed=embed)
        return True

    gifs = json.loads(row[0])
    selected_gif = random.choice(gifs) if gifs else None

    embed = discord.Embed(
        description=f"**<@{author.id}>** {action_name}s **<@{target.id}>**!",
        color=discord.Color.from_str("#2B2D31")
    )
    if selected_gif:
        embed.set_image(url=selected_gif)

    await respond_func(content=f"<@{target.id}>", embed=embed)
    return True

async def process_meter(author: discord.Member | discord.User, target: discord.Member | discord.User, meter_name_raw: str, respond_func):

    if target.id == nexus.user.id:
        embed = discord.Embed(
            description=random.choice(snark_pool.BOT_IMMUNITY_REPLIES),
            color=discord.Color.from_str("#2B2D31")
        )
        await respond_func(content=f"<@{author.id}>", embed=embed)
        return

    meter_name = meter_name_raw.lower()
    cursor = nexus.db_conn.cursor()
    cursor.execute("SELECT emoji FROM joke_meters WHERE meter_name = ?", (meter_name,))
    row = cursor.fetchone()

    if not row:
        embed = embed_formatter.create_invalid_meter_embed(author)
        await respond_func(content=f"<@{target.id}>", embed=embed)
        return

    emoji = row[0]
    score, progress_bar, snark = snark_pool.calculate_meter(target.id, meter_name, nexus.db_conn)
    embed = embed_formatter.create_meter_embed(
        author=author,
        target_id=target.id,
        meter_name=meter_name,
        emoji=emoji,
        score=score,
        progress_bar=progress_bar,
        snark=snark
    )
    await respond_func(content=f"<@{target.id}>", embed=embed)


@nexus.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if not message.content.startswith(PREFIX):
        return

    # Extract word after prefix
    content_without_prefix = message.content[len(PREFIX):].strip()
    if not content_without_prefix:
        return

    parts = content_without_prefix.split()
    meter_name_raw = parts[0]

    target = None

    # 1. Check if replying to a message
    if message.reference and message.reference.message_id:
        try:
            # We don't want to use fetch_message if cached, but we can resolve the member easily
            # if reference is cached, try to get author.
            if message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
                target = message.reference.resolved.author
            else:
                # Need to fetch
                channel = nexus.get_channel(message.reference.channel_id)
                if channel:
                    ref_msg = await channel.fetch_message(message.reference.message_id)
                    target = ref_msg.author
        except Exception:
            pass

    # 2. Check mentions
    if target is None and message.mentions:
        # Filter out bot mentions if we want, but basically take the first mention
        # that isn't the bot if possible, or just the first mention
        for mention in message.mentions:
            if not mention.bot:
                target = mention
                break
        if target is None:
            target = message.mentions[0]

    # 3. Default to author
    if target is None:
        target = message.author


    async def send_response(content, embed):
        await message.channel.send(content=content, embed=embed)

    # Check if it's an action first
    is_action = await process_action(message.author, target, meter_name_raw, send_response)
    if is_action:
        return

    await process_meter(message.author, target, meter_name_raw, send_response)


    # Make sure we do not block standard commands from firing if any are added later
    await nexus.process_commands(message)




@nexus.tree.command(name="add-action", description="Add a new roleplay joke action")
@app_commands.describe(name="The trigger word for the action (e.g., slap)", search_term="The search term to find GIFs (e.g., anime slap)")
@app_commands.default_permissions(administrator=True)
async def add_action(interaction: discord.Interaction, name: str, search_term: str):
    await interaction.response.defer(ephemeral=True)
    action_name_lower = name.lower()

    gifs = await giphy_api.fetch_giphy_gifs(search_term)
    if not gifs:
        await interaction.followup.send(f"Failed to find any GIFs for the search term '{search_term}'. Is your Giphy API key configured?")
        return

    try:
        gifs_json = json.dumps(gifs)
        cursor = nexus.db_conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO joke_actions (action_name, gifs) VALUES (?, ?)", (action_name_lower, gifs_json))
        nexus.db_conn.commit()
        await interaction.followup.send(f"Successfully added/updated action `{action_name_lower}` and fetched {len(gifs)} GIFs.")
    except Exception as e:
        await interaction.followup.send(f"Failed to add action: {e}")

@nexus.tree.command(name="remove-action", description="Remove a joke action")
@app_commands.describe(name="The trigger word of the action to remove")
@app_commands.default_permissions(administrator=True)
async def remove_action(interaction: discord.Interaction, name: str):
    action_name_lower = name.lower()
    try:
        cursor = nexus.db_conn.cursor()
        cursor.execute("DELETE FROM joke_actions WHERE action_name = ?", (action_name_lower,))
        if cursor.rowcount > 0:
            nexus.db_conn.commit()
            await interaction.response.send_message(f"Successfully removed action `{action_name_lower}`", ephemeral=True)
        else:
            await interaction.response.send_message(f"Action `{action_name_lower}` not found.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to remove action: {e}", ephemeral=True)

@nexus.tree.command(name="list-actions", description="List all available joke actions")
async def list_actions(interaction: discord.Interaction):
    try:
        cursor = nexus.db_conn.cursor()
        cursor.execute("SELECT action_name FROM joke_actions ORDER BY action_name ASC")
        rows = cursor.fetchall()

        if not rows:
            await interaction.response.send_message("No actions have been added yet.", ephemeral=True)
            return

        description = "\n".join([f"• **{name}**" for (name,) in rows])
        embed = discord.Embed(
            title="Available Joke Actions",
            description=description,
            color=discord.Color.from_str("#2B2D31")
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"Failed to list actions: {e}", ephemeral=True)

@nexus.tree.command(name="list-meters", description="List all available joke meters")
async def list_meters(interaction: discord.Interaction):
    try:
        cursor = nexus.db_conn.cursor()
        cursor.execute("SELECT meter_name, emoji FROM joke_meters ORDER BY meter_name ASC")
        rows = cursor.fetchall()

        if not rows:
            await interaction.response.send_message("No meters have been added yet.", ephemeral=True)
            return

        description = "\n".join([f"{emoji} **{name}**" for name, emoji in rows])
        embed = discord.Embed(
            title="Available Joke Meters",
            description=description,
            color=discord.Color.from_str("#2B2D31")
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"Failed to list meters: {e}", ephemeral=True)

@nexus.tree.command(name="measure", description="Measure a user's joke meter level")
@app_commands.describe(meter_name="The name of the meter to measure", user="The user to measure (defaults to yourself)")
async def measure(interaction: discord.Interaction, meter_name: str, user: discord.Member = None):
    target = user if user else interaction.user

    async def respond(content, embed):
        await interaction.response.send_message(content=content, embed=embed)

    await process_meter(interaction.user, target, meter_name, respond)

if __name__ == "__main__":
    if TOKEN and TOKEN != "your_token_here":
        nexus.run(TOKEN)
    else:
        print("Please set your DISCORD_TOKEN in the .env file.")
