import discord
from discord.ext import commands
from discord import app_commands
import json
import random
import os
from datetime import datetime, timezone

from . import embed_formatter
from . import snark_pool
from . import giphy_api
from . import ui_overrides

class CoreCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def process_action(self, author: discord.Member | discord.User, target: discord.Member | discord.User, action_name_raw: str, respond_func) -> bool:
        action_name = action_name_raw.lower()
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT gifs FROM joke_actions WHERE action_name = ?", (action_name,))
        row = cursor.fetchone()

        if not row:
            return False # Was not an action

        # Bot immunity Check
        if target.id == self.bot.user.id:
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

    async def process_meter(self, author: discord.Member | discord.User, target: discord.Member | discord.User, meter_name_raw: str, respond_func):
        meter_name = meter_name_raw.lower()

        if target.id == self.bot.user.id:
            embed = discord.Embed(
                description=random.choice(snark_pool.BOT_IMMUNITY_REPLIES),
                color=discord.Color.from_str("#2B2D31")
            )
            await respond_func(content=f"<@{author.id}>", embed=embed)
            return

        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT emoji FROM joke_meters WHERE meter_name = ?", (meter_name,))
        row = cursor.fetchone()

        if not row:
            embed = embed_formatter.create_invalid_meter_embed(author)
            await respond_func(content=f"<@{author.id}>", embed=embed)
            return

        emoji = row[0]
        score, progress_bar, snark = snark_pool.calculate_meter(target.id, meter_name, self.bot.db_conn)
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        prefix = await self.bot.get_prefix(message)
        # handle list of prefixes just in case
        if isinstance(prefix, list):
            prefix = prefix[0]

        if not message.content.startswith(prefix):
            return

        content_without_prefix = message.content[len(prefix):].strip()
        if not content_without_prefix:
            return

        parts = content_without_prefix.split()
        meter_name_raw = parts[0]

        target = None

        # 1. Check if replying to a message
        if message.reference and message.reference.message_id:
            try:
                if message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
                    target = message.reference.resolved.author
                else:
                    channel = self.bot.get_channel(message.reference.channel_id)
                    if channel:
                        ref_msg = await channel.fetch_message(message.reference.message_id)
                        target = ref_msg.author
            except Exception:
                pass

        # 2. Check mentions
        if target is None and message.mentions:
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

        is_action = await self.process_action(message.author, target, meter_name_raw, send_response)
        if is_action:
            return

        await self.process_meter(message.author, target, meter_name_raw, send_response)

        # Make sure we do not block standard commands from firing if any are added later
        # Actually in cogs context the bot handles this, but we'll leave it out since we are using app_commands anyway

    @app_commands.command(name="add-meter", description="Add a new joke meter")
    @app_commands.describe(name="The trigger word for the meter", emoji="The emoji icon for the meter")
    @app_commands.default_permissions(administrator=True)
    async def add_meter(self, interaction: discord.Interaction, name: str, emoji: str):
        meter_name_lower = name.lower()
        try:
            cursor = self.bot.db_conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO joke_meters (meter_name, emoji) VALUES (?, ?)", (meter_name_lower, emoji))
            self.bot.db_conn.commit()
            await interaction.response.send_message(f"Successfully added/updated meter `{meter_name_lower}` with emoji {emoji}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to add meter: {e}", ephemeral=True)

    @app_commands.command(name="remove-meter", description="Remove a joke meter")
    @app_commands.describe(name="The trigger word of the meter to remove")
    @app_commands.default_permissions(administrator=True)
    async def remove_meter(self, interaction: discord.Interaction, name: str):
        meter_name_lower = name.lower()
        try:
            cursor = self.bot.db_conn.cursor()
            cursor.execute("DELETE FROM joke_meters WHERE meter_name = ?", (meter_name_lower,))
            if cursor.rowcount > 0:
                self.bot.db_conn.commit()
                await interaction.response.send_message(f"Successfully removed meter `{meter_name_lower}`", ephemeral=True)
            else:
                await interaction.response.send_message(f"Meter `{meter_name_lower}` not found.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to remove meter: {e}", ephemeral=True)

    @app_commands.command(name="list-actions", description="List all available joke actions")
    async def list_actions(self, interaction: discord.Interaction):
        try:
            cursor = self.bot.db_conn.cursor()
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

    @app_commands.command(name="list-meters", description="List all available joke meters")
    async def list_meters(self, interaction: discord.Interaction):
        try:
            cursor = self.bot.db_conn.cursor()
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

    @app_commands.command(name="add-action", description="Add a new roleplay joke action")
    @app_commands.describe(name="The trigger word for the action (e.g., slap)", search_term="The search term to find GIFs (e.g., anime slap)")
    @app_commands.default_permissions(administrator=True)
    async def add_action(self, interaction: discord.Interaction, name: str, search_term: str):
        await interaction.response.defer(ephemeral=True)
        action_name_lower = name.lower()

        gifs = await giphy_api.fetch_giphy_gifs(search_term)
        if not gifs:
            await interaction.followup.send(f"Failed to find any GIFs for the search term '{search_term}'. Is your Giphy API key configured?")
            return

        try:
            gifs_json = json.dumps(gifs)
            cursor = self.bot.db_conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO joke_actions (action_name, gifs) VALUES (?, ?)", (action_name_lower, gifs_json))
            self.bot.db_conn.commit()
            await interaction.followup.send(f"Successfully added/updated action `{action_name_lower}` and fetched {len(gifs)} GIFs.")
        except Exception as e:
            await interaction.followup.send(f"Failed to add action: {e}")

    @app_commands.command(name="remove-action", description="Remove a joke action")
    @app_commands.describe(name="The trigger word of the action to remove")
    @app_commands.default_permissions(administrator=True)
    async def remove_action(self, interaction: discord.Interaction, name: str):
        action_name_lower = name.lower()
        try:
            cursor = self.bot.db_conn.cursor()
            cursor.execute("DELETE FROM joke_actions WHERE action_name = ?", (action_name_lower,))
            if cursor.rowcount > 0:
                self.bot.db_conn.commit()
                await interaction.response.send_message(f"Successfully removed action `{action_name_lower}`", ephemeral=True)
            else:
                await interaction.response.send_message(f"Action `{action_name_lower}` not found.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to remove action: {e}", ephemeral=True)

    @app_commands.command(name="measure", description="Measure a user's joke meter level")
    @app_commands.describe(meter_name="The name of the meter to measure", user="The user to measure (defaults to yourself)")
    async def measure(self, interaction: discord.Interaction, meter_name: str, user: discord.Member = None):
        target = user if user else interaction.user

        async def respond(content, embed):
            await interaction.response.send_message(content=content, embed=embed)

        await self.process_meter(interaction.user, target, meter_name, respond)

    @app_commands.command(name="perform", description="Perform a joke action on a user")
    @app_commands.describe(action_name="The name of the action to perform", user="The user to target")
    async def perform(self, interaction: discord.Interaction, action_name: str, user: discord.Member = None):
        target = user if user else interaction.user

        async def respond(content, embed):
            await interaction.response.send_message(content=content, embed=embed)

        is_action = await self.process_action(interaction.user, target, action_name, respond)
        if not is_action:
            embed = embed_formatter.create_invalid_meter_embed(interaction.user)
            await respond(content=f"<@{interaction.user.id}>", embed=embed)

    @app_commands.command(name="override-scores", description="[OWNER ONLY] Edit a user's daily meter scores")
    @app_commands.describe(user="The user to edit")
    async def override_scores(self, interaction: discord.Interaction, user: discord.Member):
        owner_id = os.getenv("OWNER_ID")
        if str(interaction.user.id) != str(owner_id):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT meter_name, emoji FROM joke_meters ORDER BY meter_name ASC")
        rows = cursor.fetchall()

        if not rows:
            await interaction.response.send_message("No meters available to override.", ephemeral=True)
            return

        meter_names = [row[0] for row in rows]

        def generate_embed():
            description_lines = []
            for name, emoji in rows:
                score, _, _ = snark_pool.calculate_meter(user.id, name, self.bot.db_conn)
                utc_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                cursor.execute("SELECT score FROM score_overrides WHERE target_id = ? AND meter_name = ? AND utc_date = ?", (user.id, name, utc_date))
                override = cursor.fetchone()

                is_overridden = " *(Edited)*" if override else ""
                description_lines.append(f"{emoji} **{name.capitalize()}**: {score}%{is_overridden}")

            embed = discord.Embed(
                title=f"Score Overrides for {user.display_name}",
                description="\n".join(description_lines),
                color=discord.Color.from_str("#2B2D31")
            )
            return embed

        view = ui_overrides.OverrideView(self.bot.db_conn, user, meter_names, generate_embed)
        embed = generate_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(CoreCommands(bot))
