import discord
from discord.ext import commands, tasks
import sqlite3
import datetime
import os
import psutil
from . import embed_factory

class LiveStatus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.process = psutil.Process()

        # Ensure table exists
        cursor = self.bot.db_conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS live_status (
                channel_id INTEGER,
                message_id INTEGER PRIMARY KEY
            )
        ''')
        self.bot.db_conn.commit()

        self.live_status_loop.start()

    def cog_unload(self):
        self.live_status_loop.cancel()

    def is_owner(self, ctx):
        owner_id = os.getenv("OWNER_ID")
        return str(ctx.author.id) == str(owner_id)

    @commands.hybrid_command(name="live-status", description="[OWNER] Spawn a live updating status message")
    async def live_status(self, ctx: commands.Context):
        if not self.is_owner(ctx):
            await ctx.send("Access denied.", ephemeral=True)
            return

        embed, view = self.generate_live_status_content()
        msg = await ctx.send(embed=embed, view=view)

        # Save to DB
        cursor = self.bot.db_conn.cursor()
        cursor.execute("INSERT INTO live_status (channel_id, message_id) VALUES (?, ?)", (ctx.channel.id, msg.id))
        self.bot.db_conn.commit()

        await ctx.send("Live status message created and registered.", ephemeral=True)

    def generate_live_status_content(self):
        # Scale
        guilds = len(self.bot.guilds)
        users = sum(g.member_count for g in self.bot.guilds if g.member_count)
        channels = sum(len(g.channels) for g in self.bot.guilds)

        # Uptime
        now = datetime.datetime.now(datetime.timezone.utc)
        uptime_delta = now - getattr(self.bot.cogs.get('Utility', self), 'start_time', now)
        days, remainder = divmod(int(uptime_delta.total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days} days, {hours} hours, {minutes} minutes"

        # Latency
        ws_latency = round(self.bot.latency * 1000)

        content = f"**📊 General Statistics**\n"
        content += f"**Servers:** `{guilds}`\n"
        content += f"**Users:** `{users:,}`\n"
        content += f"**Channels:** `{channels:,}`\n\n"

        content += f"**❤️ Health & Responsiveness**\n"
        content += f"**Uptime:** `{uptime_str}`\n"
        content += f"**Ping:** `{ws_latency}ms`\n\n"

        content += f"**🤖 Bot Identity & Resources**\n"
        content += f"**Version:** `v2.1.0`\n"
        content += f"**Library:** `Powered by discord.py`\n"
        content += f"**Creator:** `Created by @Angrytoast`\n"

        embed = embed_factory.create_clean_embed("🟢 Project Nexus Live Status", content)
        embed.set_footer(text=f"Last Updated: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="Support Server", url="https://discord.gg/J4SHrpcKaK", style=discord.ButtonStyle.link))
        # Use our invite link that has OAuth joined logic
        view.add_item(discord.ui.Button(label="Invite Bot", url="https://nexuscore.wisp.uno/bot-invite", style=discord.ButtonStyle.link))

        return embed, view

    @tasks.loop(seconds=60)
    async def live_status_loop(self):
        await self.bot.wait_until_ready()

        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT channel_id, message_id FROM live_status")
        rows = cursor.fetchall()

        if not rows:
            return

        embed, view = self.generate_live_status_content()

        for row in rows:
            try:
                channel = self.bot.get_channel(row[0])
                if channel:
                    msg = await channel.fetch_message(row[1])
                    await msg.edit(embed=embed, view=view)
                else:
                    # Could try fetching via API if not in cache, but let's skip to avoid rate limits on dead messages
                    pass
            except discord.NotFound:
                # Message was deleted, remove from DB
                cursor.execute("DELETE FROM live_status WHERE message_id = ?", (row[1],))
                self.bot.db_conn.commit()
            except Exception as e:
                print(f"Failed to update live status: {e}")

async def setup(bot):
    await bot.add_cog(LiveStatus(bot))
