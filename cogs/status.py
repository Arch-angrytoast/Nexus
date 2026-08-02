import discord
from discord.ext import commands, tasks
import itertools

import os
import itertools

class StatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status_index = 0

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.rotate_status.is_running():
            self.rotate_status.start()

    def cog_unload(self):
        self.rotate_status.cancel()

    @tasks.loop(seconds=15.0)
    async def rotate_status(self):
        try:
            if not os.path.exists("statuses.txt"):
                return

            with open("statuses.txt", "r") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]

            if not lines:
                return

            if self.status_index >= len(lines):
                self.status_index = 0

            current_status = lines[self.status_index]
            self.status_index += 1

            activity_type = discord.ActivityType.playing
            name = current_status

            if "|" in current_status:
                parts = current_status.split("|", 1)
                t_str = parts[0].strip().lower()
                name = parts[1].strip()

                if t_str == "watching":
                    activity_type = discord.ActivityType.watching
                elif t_str == "listening":
                    activity_type = discord.ActivityType.listening
                elif t_str == "competing":
                    activity_type = discord.ActivityType.competing

            activity = discord.Activity(type=activity_type, name=name)
            if not self.bot.is_closed():
                await self.bot.change_presence(status=discord.Status.dnd, activity=activity)
        except RuntimeError as e:
            if "Cannot write to closing transport" in str(e):
                pass # Silently ignore websocket drops while reconnecting
            else:
                print(f"Status rotation runtime error: {e}")
        except Exception as e:
            print(f"Status rotation error: {e}")

    @rotate_status.before_loop
    async def before_rotate(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(StatusCog(bot))
