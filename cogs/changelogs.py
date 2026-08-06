import discord
from discord.ext import commands
import sqlite3
import os

class Changelogs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Ensure table exists
        cursor = self.bot.db_conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS changelog_config (
                id INTEGER PRIMARY KEY DEFAULT 1,
                channel_id INTEGER
            )
        ''')
        self.bot.db_conn.commit()

    def is_owner(self, ctx):
        owner_id = os.getenv("OWNER_ID")
        return str(ctx.author.id) == str(owner_id)

    @commands.hybrid_group(name="changelogs", description="[OWNER] Manage changelog settings")
    async def changelogs(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `/changelogs set <channel>` to configure.", ephemeral=True)

    @changelogs.command(name="set", description="[OWNER] Set the channel for GitHub webhook push events")
    async def changelogs_set(self, ctx: commands.Context, channel: discord.TextChannel):
        if not self.is_owner(ctx):
            await ctx.send("Access denied.", ephemeral=True)
            return

        cursor = self.bot.db_conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO changelog_config (id, channel_id) VALUES (1, ?)", (channel.id,))
        self.bot.db_conn.commit()

        await ctx.send(f"Changelogs will now be posted in {channel.mention}.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Changelogs(bot))
