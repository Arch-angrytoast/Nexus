import discord
from discord.ext import commands, tasks
import time
import io
import aiohttp
import sqlite3
import datetime
from . import embed_factory

class DelaySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="30 Minutes", value="1800"),
            discord.SelectOption(label="1 Hour", value="3600"),
            discord.SelectOption(label="2 Hours", value="7200"),
            discord.SelectOption(label="6 Hours", value="21600"),
            discord.SelectOption(label="12 Hours", value="43200"),
            discord.SelectOption(label="24 Hours", value="86400"),
            discord.SelectOption(label="48 Hours", value="172800")
        ]
        super().__init__(placeholder="Select shuffle delay...", min_values=1, max_values=1, options=options, custom_id="iconshuffle_delay")

    async def callback(self, interaction: discord.Interaction):
        delay = int(self.values[0])
        cursor = self.view.db_conn.cursor()
        cursor.execute("UPDATE iconshuffle_config SET delay_seconds = ? WHERE guild_id = ?", (delay, str(interaction.guild_id)))
        self.view.db_conn.commit()
        await self.view.refresh_ui(interaction, f"Delay updated to {delay} seconds.")


class OrderSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Sequential", value="sequential", description="Rotate in the order added"),
            discord.SelectOption(label="Random", value="random", description="Pick a random icon next")
        ]
        super().__init__(placeholder="Select shuffle order...", min_values=1, max_values=1, options=options, custom_id="iconshuffle_order")

    async def callback(self, interaction: discord.Interaction):
        order = self.values[0]
        cursor = self.view.db_conn.cursor()
        cursor.execute("UPDATE iconshuffle_config SET shuffle_order = ? WHERE guild_id = ?", (order, str(interaction.guild_id)))
        self.view.db_conn.commit()
        await self.view.refresh_ui(interaction, f"Order updated to {order}.")

class IconShuffleView(discord.ui.View):
    def __init__(self, bot, guild, db_conn):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild = guild
        self.db_conn = db_conn

        self.add_item(DelaySelect())
        self.add_item(OrderSelect())

        cursor = self.db_conn.cursor()
        cursor.execute("SELECT enabled FROM iconshuffle_config WHERE guild_id = ?", (str(guild.id),))
        row = cursor.fetchone()
        self.enabled = row[0] == 1 if row else False

        self.enable_btn = discord.ui.Button(label="Disable" if self.enabled else "Enable", style=discord.ButtonStyle.danger if self.enabled else discord.ButtonStyle.success, custom_id="iconshuffle_enable")
        self.enable_btn.callback = self.toggle_enable
        self.add_item(self.enable_btn)

        self.add_icon_btn = discord.ui.Button(label="Add Icon", style=discord.ButtonStyle.primary, custom_id="iconshuffle_add")
        self.add_icon_btn.callback = self.add_icon_prompt
        self.add_item(self.add_icon_btn)

        self.remove_icon_btn = discord.ui.Button(label="Remove Last Icon", style=discord.ButtonStyle.secondary, custom_id="iconshuffle_remove")
        self.remove_icon_btn.callback = self.remove_icon
        self.add_item(self.remove_icon_btn)

    async def toggle_enable(self, interaction: discord.Interaction):
        self.enabled = not self.enabled
        cursor = self.db_conn.cursor()
        cursor.execute("UPDATE iconshuffle_config SET enabled = ? WHERE guild_id = ?", (1 if self.enabled else 0, str(interaction.guild_id)))
        self.db_conn.commit()
        await self.refresh_ui(interaction, f"Icon Shuffle {'enabled' if self.enabled else 'disabled'}.")

    async def add_icon_prompt(self, interaction: discord.Interaction):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT count(*) FROM iconshuffle_icons WHERE guild_id = ?", (str(interaction.guild_id),))
        count = cursor.fetchone()[0]
        if count >= 20:
            await interaction.response.send_message("You have reached the maximum limit of 20 icons.", ephemeral=True)
            return

        await interaction.response.send_message("Please upload an image in this channel within 60 seconds.", ephemeral=True)

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel and len(m.attachments) > 0

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            attachment = msg.attachments[0]

            # Fetch storage server
            cursor.execute("SELECT value FROM global_config WHERE key = 'storage_server_id'")
            storage_server_id_row = cursor.fetchone()
            if not storage_server_id_row:
                await interaction.followup.send("Storage server is not configured by the bot owner. Cannot add icons.", ephemeral=True)
                return

            storage_server = self.bot.get_guild(int(storage_server_id_row[0]))
            if not storage_server:
                await interaction.followup.send("Cannot access the storage server.", ephemeral=True)
                return

            # Read attachment bytes
            try:
                image_bytes = await attachment.read()
            except Exception:
                await interaction.followup.send("Failed to read the image.", ephemeral=True)
                return

            # Find or create category and channel
            cursor.execute("SELECT storage_category_id, storage_channel_id FROM iconshuffle_config WHERE guild_id = ?", (str(interaction.guild_id),))
            config_row = cursor.fetchone()
            cat_id, chan_id = config_row[0], config_row[1]

            storage_category = storage_server.get_channel(int(cat_id)) if cat_id else None
            if not storage_category:
                storage_category = await storage_server.create_category(name=f"Guild_{interaction.guild_id}")
                cat_id = str(storage_category.id)
                cursor.execute("UPDATE iconshuffle_config SET storage_category_id = ? WHERE guild_id = ?", (cat_id, str(interaction.guild_id)))

            storage_channel = storage_server.get_channel(int(chan_id)) if chan_id else None
            if not storage_channel:
                storage_channel = await storage_server.create_text_channel(name="icons", category=storage_category)
                chan_id = str(storage_channel.id)
                cursor.execute("UPDATE iconshuffle_config SET storage_channel_id = ? WHERE guild_id = ?", (chan_id, str(interaction.guild_id)))

            # Upload to storage channel
            file = discord.File(io.BytesIO(image_bytes), filename=attachment.filename)
            stored_msg = await storage_channel.send(file=file)

            # Save into our DB
            cursor.execute("INSERT INTO iconshuffle_icons (guild_id, channel_id, message_id) VALUES (?, ?, ?)", (str(interaction.guild_id), chan_id, str(stored_msg.id)))
            self.db_conn.commit()

            try:
                await msg.delete()
            except Exception:
                pass

            await interaction.followup.send("Successfully added the icon!", ephemeral=True)
            # Re-fetch config to refresh UI properly
            class FakeInt:
                class Resp:
                    def is_done(self): return True
                    async def edit_message(self, **kwargs): pass
                response = Resp()
                async def edit_original_response(self, **kwargs):
                    await interaction.edit_original_response(**kwargs)
            await self.refresh_ui(FakeInt())

        except Exception as e:
            await interaction.followup.send(f"Failed or timed out: {str(e)}", ephemeral=True)

    async def remove_icon(self, interaction: discord.Interaction):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT id FROM iconshuffle_icons WHERE guild_id = ? ORDER BY id DESC LIMIT 1", (str(interaction.guild_id),))
        row = cursor.fetchone()
        if not row:
            await interaction.response.send_message("No icons to remove.", ephemeral=True)
            return

        cursor.execute("DELETE FROM iconshuffle_icons WHERE id = ?", (row[0],))
        self.db_conn.commit()
        await self.refresh_ui(interaction, "Removed the last added icon.")

    async def refresh_ui(self, interaction: discord.Interaction, message: str = ""):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT enabled, delay_seconds, shuffle_order FROM iconshuffle_config WHERE guild_id = ?", (str(self.guild.id),))
        config = cursor.fetchone()

        cursor.execute("SELECT count(*) FROM iconshuffle_icons WHERE guild_id = ?", (str(self.guild.id),))
        icons_count = cursor.fetchone()[0]

        if config:
            enabled, delay, order = config
        else:
            enabled, delay, order = 0, 3600, 'sequential'

        embed = embed_factory.create_clean_embed("🖼️ Icon Shuffle Configuration", "")
        embed.add_field(name="Status", value="✅ Enabled" if enabled else "❌ Disabled")
        embed.add_field(name="Delay", value=f"{delay // 60} minutes")
        embed.add_field(name="Order", value=order.capitalize())
        embed.add_field(name="Icons Loaded", value=f"{icons_count} / 20")
        if message:
            embed.set_footer(text=message)

        self.enable_btn.label = "Disable" if enabled else "Enable"
        self.enable_btn.style = discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success

        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            pass

class IconShuffle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.shuffler_task.start()

    def cog_unload(self):
        self.shuffler_task.cancel()

    def ensure_config(self, guild_id: str):
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT guild_id FROM iconshuffle_config WHERE guild_id = ?", (guild_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO iconshuffle_config (guild_id) VALUES (?)", (guild_id,))
            self.bot.db_conn.commit()

    @commands.hybrid_command(name="iconshuffle", description="Configure server icon shuffling")
    @commands.has_permissions(manage_guild=True)
    async def iconshuffle(self, ctx: commands.Context):
        self.ensure_config(str(ctx.guild.id))
        view = IconShuffleView(self.bot, ctx.guild, self.bot.db_conn)

        # Manually trigger a refresh to get the initial embed populated
        class FakeInteraction:
            class Response:
                def is_done(self): return False
                async def edit_message(self, **kwargs): pass
            response = Response()

        await view.refresh_ui(FakeInteraction())

        # We need to recreate the initial embed the same way refresh_ui does to match
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT enabled, delay_seconds, shuffle_order FROM iconshuffle_config WHERE guild_id = ?", (str(ctx.guild.id),))
        config = cursor.fetchone()
        cursor.execute("SELECT count(*) FROM iconshuffle_icons WHERE guild_id = ?", (str(ctx.guild.id),))
        icons_count = cursor.fetchone()[0]

        enabled, delay, order = config if config else (0, 3600, 'sequential')
        embed = embed_factory.create_clean_embed("🖼️ Icon Shuffle Configuration", "")
        embed.add_field(name="Status", value="✅ Enabled" if enabled else "❌ Disabled")
        embed.add_field(name="Delay", value=f"{delay // 60} minutes")
        embed.add_field(name="Order", value=order.capitalize())
        embed.add_field(name="Icons Loaded", value=f"{icons_count} / 20")

        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name="iconshuffle-conf", description="Edit server icon shuffling configuration")
    @commands.has_permissions(manage_guild=True)
    async def iconshuffle_conf(self, ctx: commands.Context):
        await self.iconshuffle(ctx)

    @tasks.loop(minutes=5)
    async def shuffler_task(self):
        cursor = self.bot.db_conn.cursor()

        # Get storage server
        cursor.execute("SELECT value FROM global_config WHERE key = 'storage_server_id'")
        storage_server_id_row = cursor.fetchone()
        if not storage_server_id_row:
            return

        storage_server = self.bot.get_guild(int(storage_server_id_row[0]))
        if not storage_server:
            return

        cursor.execute("SELECT guild_id, delay_seconds, shuffle_order, last_shuffle, current_index FROM iconshuffle_config WHERE enabled = 1")
        configs = cursor.fetchall()

        now = datetime.datetime.now(datetime.timezone.utc)

        for config in configs:
            guild_id, delay_seconds, shuffle_order, last_shuffle_str, current_index = config
            try:
                last_shuffle = datetime.datetime.strptime(last_shuffle_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                last_shuffle = datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)

            if (now - last_shuffle).total_seconds() >= delay_seconds:
                # Time to shuffle
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    continue

                cursor.execute("SELECT id, channel_id, message_id FROM iconshuffle_icons WHERE guild_id = ? ORDER BY id ASC", (guild_id,))
                icons = cursor.fetchall()
                if not icons:
                    continue

                if shuffle_order == 'random':
                    import random
                    next_icon = random.choice(icons)
                    next_index = current_index
                else:
                    next_index = (current_index + 1) % len(icons)
                    next_icon = icons[next_index]

                _, channel_id, message_id = next_icon

                try:
                    storage_channel = storage_server.get_channel(int(channel_id))
                    if storage_channel:
                        msg = await storage_channel.fetch_message(int(message_id))
                        if msg.attachments:
                            image_bytes = await msg.attachments[0].read()
                            await guild.edit(icon=image_bytes)

                            # Update config
                            cursor.execute("UPDATE iconshuffle_config SET last_shuffle = ?, current_index = ? WHERE guild_id = ?",
                                           (now.strftime("%Y-%m-%d %H:%M:%S"), next_index, guild_id))
                            self.bot.db_conn.commit()
                except Exception as e:
                    print(f"Failed to shuffle icon for guild {guild_id}: {e}")

    @shuffler_task.before_loop
    async def before_shuffler_task(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(IconShuffle(bot))
