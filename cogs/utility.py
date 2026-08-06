import discord
from discord.ext import commands
import os
import psutil
import datetime
import sqlite3
from . import embed_factory

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        self.process = psutil.Process()

    def is_owner(self, ctx):
        owner_id = os.getenv("OWNER_ID")
        return str(ctx.author.id) == str(owner_id)

    @commands.hybrid_command(name="status", description="[OWNER] View detailed bot and host status")
    async def status(self, ctx: commands.Context):
        if not self.is_owner(ctx):
            await ctx.send("Access denied.", ephemeral=True)
            return

        # System & Host Resources
        import platform
        import time

        # CPU
        bot_cpu = self.process.cpu_percent()
        sys_cpu = psutil.cpu_percent()

        # Memory
        mem = psutil.virtual_memory()
        bot_ram_mb = self.process.memory_info().rss / 1024 / 1024
        total_ram_gb = mem.total / (1024**3)
        used_ram_gb = mem.used / (1024**3)

        host_os = f"{platform.system()} {platform.release()}"

        # Performance & Uptime
        now = datetime.datetime.now(datetime.timezone.utc)
        uptime_delta = now - self.start_time
        days, remainder = divmod(int(uptime_delta.total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m"

        ws_latency = round(self.bot.latency * 1000)

        # API Latency calculation
        api_start = time.perf_counter()
        msg = await ctx.send("Pinging API...", ephemeral=True)
        api_end = time.perf_counter()
        api_latency = round((api_end - api_start) * 1000)

        # DB Latency calculation
        db_start = time.perf_counter()
        try:
            cursor = self.bot.db_conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            db_end = time.perf_counter()
            db_latency = round((db_end - db_start) * 1000)
            db_status = f"🟢 Healthy ({db_latency}ms)"
        except Exception as e:
            db_status = f"🔴 Offline/Error"

        # Scale & Analytics
        guilds = len(self.bot.guilds)
        users = sum(g.member_count for g in self.bot.guilds if g.member_count)
        channels = sum(len(g.channels) for g in self.bot.guilds)
        shard_info = f"Shard {self.bot.shard_id or 0} of {self.bot.shard_count or 1}"

        # Environment Specs
        py_ver = platform.python_version()
        dpy_ver = discord.__version__

        # Build Embed
        embed = embed_factory.create_clean_embed("🤖 System Status", "")

        embed.add_field(name="💻 System & Host", value=f"**OS:** {host_os}\n**CPU (Bot):** {bot_cpu}% | **(Sys):** {sys_cpu}%\n**RAM (Bot):** {bot_ram_mb:.2f} MB\n**RAM (Sys):** {used_ram_gb:.2f}GB / {total_ram_gb:.2f}GB", inline=False)
        embed.add_field(name="⏱️ Performance", value=f"**Uptime:** {uptime_str}\n**WebSocket Ping:** {ws_latency}ms\n**API Latency:** {api_latency}ms\n**Database:** {db_status}", inline=False)
        embed.add_field(name="📈 Scale & Analytics", value=f"**Servers:** {guilds}\n**Users:** {users:,}\n**Channels:** {channels:,}\n**Shards:** {shard_info}", inline=False)
        embed.add_field(name="🛠️ Environment", value=f"**Python:** v{py_ver}\n**Library:** discord.py v{dpy_ver}", inline=False)

        await msg.edit(content=None, embed=embed)

    @commands.hybrid_command(name="uptime", description="[OWNER] View how long the bot has been online")
    async def uptime(self, ctx: commands.Context):
        if not self.is_owner(ctx):
            await ctx.send("Access denied.", ephemeral=True)
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        uptime_delta = now - self.start_time

        days, remainder = divmod(int(uptime_delta.total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        start_timestamp = int(self.start_time.timestamp())

        content = f"**Online For:** {uptime_str}\n"
        content += f"**Started At:** <t:{start_timestamp}:F> (<t:{start_timestamp}:R>)"

        embed = embed_factory.create_clean_embed("⏱️ Bot Uptime", content)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="diagnostics", description="[OWNER] Run a full system diagnostic check")
    async def diagnostics(self, ctx: commands.Context):
        if not self.is_owner(ctx):
            await ctx.send("Access denied.", ephemeral=True)
            return

        # Get DB size
        db_size_kb = os.path.getsize("bot_data.db") / 1024 if os.path.exists("bot_data.db") else 0

        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT count(*) FROM warnings")
        warnings_count = cursor.fetchone()[0]

        cursor.execute("SELECT count(*) FROM joke_meters")
        meters_count = cursor.fetchone()[0]

        cursor.execute("SELECT count(*) FROM tickets WHERE status = 'open'")
        tickets_count = cursor.fetchone()[0]

        loaded_cogs = ", ".join([cog for cog in self.bot.cogs.keys()])

        content = "**📁 Database Health**\n"
        content += f"Size: `{db_size_kb:.2f} KB`\n"
        content += f"Logged Warnings: `{warnings_count}`\n"
        content += f"Configured Meters: `{meters_count}`\n"
        content += f"Open Tickets: `{tickets_count}`\n\n"

        content += "**🧩 Application State**\n"
        content += f"Loaded Cogs: `{loaded_cogs}`\n"
        content += f"Intents Registered: `message_content, members, presences`\n"
        content += f"Host Architecture: `{os.uname().machine}`\n"

        embed = embed_factory.create_clean_embed("🔧 System Diagnostics", content)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="server-insights", description="[OWNER] View deep analytics for the current server")
    async def server_insights(self, ctx: commands.Context):
        if not self.is_owner(ctx):
            await ctx.send("Access denied.", ephemeral=True)
            return

        guild = ctx.guild
        member_count = guild.member_count
        bot_count = len([m for m in guild.members if m.bot])
        human_count = member_count - bot_count

        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        roles_count = len(guild.roles)

        # Calculate recent joins (last 24 hours)
        now = datetime.datetime.now(datetime.timezone.utc)
        one_day_ago = now - datetime.timedelta(days=1)
        recent_joins = len([m for m in guild.members if m.joined_at and m.joined_at > one_day_ago])

        content = f"**👥 Member Demographics**\n"
        content += f"Total: `{member_count}` | Humans: `{human_count}` | Bots: `{bot_count}`\n"
        content += f"Joined Last 24h: `{recent_joins}`\n\n"

        content += f"**🗺️ Server Topology**\n"
        content += f"Categories: `{categories}`\n"
        content += f"Text Channels: `{text_channels}` | Voice Channels: `{voice_channels}`\n"
        content += f"Roles: `{roles_count}` | Emojis: `{len(guild.emojis)}/{guild.emoji_limit}`\n\n"

        content += f"**🔒 Security Settings**\n"
        content += f"Verification Level: `{str(guild.verification_level).capitalize()}`\n"
        content += f"Explicit Content Filter: `{str(guild.explicit_content_filter).replace('_', ' ').title()}`"

        embed = embed_factory.create_clean_embed(f"📊 Insights: {guild.name}", content, thumbnail_url=guild.icon.url if guild.icon else None)
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Utility(bot))
