import discord
from discord.ext import commands
import time
import math
import asyncio

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}
        # Ensure schema exists
        self.bot.db_conn.execute('''
            CREATE TABLE IF NOT EXISTS leveling_users (
                user_id INTEGER PRIMARY KEY,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0
            )
        ''')
        self.bot.db_conn.execute('''
            CREATE TABLE IF NOT EXISTS leveling_rewards (
                level INTEGER PRIMARY KEY,
                role_id TEXT
            )
        ''')
        self.bot.db_conn.commit()

    def get_xp_config(self):
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT key, value FROM server_config WHERE key IN ('xp_min', 'xp_max', 'xp_cooldown', 'leveling_whitelist', 'leveling_blacklist')")
        rows = cursor.fetchall()
        config = {'xp_min': 15, 'xp_max': 25, 'xp_cooldown': 60, 'leveling_whitelist': '', 'leveling_blacklist': ''}
        for r in rows:
            if r[0] in ['xp_min', 'xp_max', 'xp_cooldown']:
                config[r[0]] = int(r[1])
            else:
                config[r[0]] = str(r[1])
        return config

    def get_rewards(self):
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT level, role_id FROM leveling_rewards ORDER BY level ASC")
        return cursor.fetchall()

    def calc_xp_for_level(self, level):
        return 5 * (level ** 2) + (50 * level) + 100

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        user_id = message.author.id
        config = self.get_xp_config()

        # Check whitelist/blacklist
        channel_id = str(message.channel.id)
        if config['leveling_whitelist']:
            whitelisted = [x.strip() for x in config['leveling_whitelist'].split(',')]
            if channel_id not in whitelisted:
                return

        if config['leveling_blacklist']:
            blacklisted = [x.strip() for x in config['leveling_blacklist'].split(',')]
            if channel_id in blacklisted:
                return

        # Check cooldown
        current_time = time.time()
        if user_id in self.cooldowns:
            if current_time - self.cooldowns[user_id] < config['xp_cooldown']:
                return

        self.cooldowns[user_id] = current_time

        import random
        xp_gain = random.randint(config['xp_min'], config['xp_max'])

        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT xp, level FROM leveling_users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

        if row:
            current_xp, current_level = row
            new_xp = current_xp + xp_gain
            cursor.execute("UPDATE leveling_users SET xp = ? WHERE user_id = ?", (new_xp, user_id))
        else:
            new_xp = xp_gain
            current_level = 0
            cursor.execute("INSERT INTO leveling_users (user_id, xp, level) VALUES (?, ?, ?)", (user_id, new_xp, current_level))

        self.bot.db_conn.commit()

        # Check for level up
        xp_needed = self.calc_xp_for_level(current_level)
        if new_xp >= xp_needed:
            new_level = current_level + 1
            cursor.execute("UPDATE leveling_users SET level = ? WHERE user_id = ?", (new_level, user_id))
            self.bot.db_conn.commit()

            # Announce
            try:
                await message.channel.send(f"🎉 **{message.author.mention}** just leveled up to **Level {new_level}**!")
            except:
                pass # Missing perms

            # Apply Role Rewards
            rewards = self.get_rewards()
            for r_level, r_role_id in rewards:
                if new_level >= r_level:
                    role = message.guild.get_role(int(r_role_id))
                    if role and role not in message.author.roles:
                        try:
                            await message.author.add_roles(role, reason=f"Level {new_level} Reward")
                        except Exception as e:
                            print(f"Failed to add role reward: {e}")

    @commands.hybrid_command(name="rank", description="Check your current level and XP.")
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT xp, level FROM leveling_users WHERE user_id = ?", (member.id,))
        row = cursor.fetchone()

        if not row:
            return await ctx.send(f"{member.display_name} has not earned any XP yet.")

        xp, level = row
        next_xp = self.calc_xp_for_level(level)

        embed = discord.Embed(title=f"Rank: {member.display_name}", color=discord.Color.from_str("#2B2D31"))
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="XP", value=f"{xp} / {next_xp}", inline=True)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Leveling(bot))
