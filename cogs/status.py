import discord
from discord.ext import commands, tasks
import itertools

class StatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # A list of statuses to rotate through
        self.statuses = itertools.cycle([
            discord.Game(name="with Joke Meters 🃏"),
            discord.Activity(type=discord.ActivityType.watching, name="over the server 🛡️"),
            discord.Activity(type=discord.ActivityType.listening, name="to !help 📜"),
            discord.Game(name="enforcing the rules ⚖️")
        ])

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.rotate_status.is_running():
            self.rotate_status.start()

    def cog_unload(self):
        self.rotate_status.cancel()

    @tasks.loop(seconds=15.0)
    async def rotate_status(self):
        try:
            status_obj = next(self.statuses)
            await self.bot.change_presence(activity=status_obj)
        except Exception:
            pass

    @rotate_status.before_loop
    async def before_rotate(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(StatusCog(bot))
