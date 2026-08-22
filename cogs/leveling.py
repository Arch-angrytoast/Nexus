import discord
from discord.ext import commands
import time
import math
import asyncio

from discord.ext import tasks

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}
        self.voice_sessions = {}
        self.xp_cache = {}  # In-memory cache {user_id: pending_xp}
        self.active_drops = {} # {guild_id: {'multiplier': float, 'expires_at': float}}
        self.xp_freezes = {} # {user_id: timestamp_expires}

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
                guild_id TEXT,
                level INTEGER,
                role_id TEXT,
                PRIMARY KEY (guild_id, level)
            )
        ''')
        self.bot.db_conn.execute('''
            CREATE TABLE IF NOT EXISTS leveling_multipliers (
                guild_id TEXT,
                role_id TEXT,
                multiplier REAL,
                PRIMARY KEY (guild_id, role_id)
            )
        ''')
        self.bot.db_conn.commit()
        self.flush_cache.start()
        self.voice_xp_loop.start()
        self.level_audit_loop.start()

    def cog_unload(self):
        self.flush_cache.cancel()
        self.voice_xp_loop.cancel()
        self.level_audit_loop.cancel()
        # Perform one final sync on unload
        asyncio.create_task(self.sync_cache_to_db())

    def get_xp_config(self, guild_id=None):
        cursor = self.bot.db_conn.cursor()
        keys = [
            "xp_min", "xp_max", "xp_cooldown", "leveling_whitelist", "leveling_blacklist",
            "leveling_role_blacklist", "leveling_min_length", "leveling_announcement_channel",
            "leveling_custom_message", "leveling_role_stacking", "module_leveling"
        ]

        if guild_id:
            keys_placeholders = ",".join(["?"]*len(keys))
            query = f"SELECT key, value FROM server_config WHERE key IN ({keys_placeholders}) AND guild_id = ?"
            query_params = keys + [str(guild_id)]
            cursor.execute(query, query_params)
        else:
            # Fallback for old single server setups
            keys_placeholders = ",".join(["?"]*len(keys))
            query = f"SELECT key, value FROM server_config WHERE key IN ({keys_placeholders})"
            cursor.execute(query, keys)

        rows = cursor.fetchall()

        config = {
            "xp_min": 15, "xp_max": 25, "xp_cooldown": 60, "leveling_whitelist": "", "leveling_blacklist": "",
            "leveling_role_blacklist": "", "leveling_min_length": 5, "leveling_announcement_channel": "current",
            "leveling_custom_message": "🎉 **{user}** just leveled up to **Level {level}**!",
            "leveling_role_stacking": "stack",
            "module_leveling": "1"
        }

        for r in rows:
            if r[0] in ['xp_min', 'xp_max', 'xp_cooldown', 'leveling_min_length']:
                config[r[0]] = int(r[1])
            else:
                config[r[0]] = str(r[1])

        return config

    async def check_permissions_and_cooldown(self, member, channel_id, config, message_length=None):
        # 0. Check Toxicity Freeze
        if member.id in self.xp_freezes:
            if datetime.datetime.now().timestamp() < self.xp_freezes[member.id]:
                return False
            else:
                del self.xp_freezes[member.id]

        # 1. Check Master Toggle
        if config.get("module_leveling", "1") == "0":
            return False

        # 2. Check Min Length
        if message_length is not None and message_length < config.get("leveling_min_length", 5):
            return False

        # Check role blacklist
        if config.get('leveling_role_blacklist'):
            role_blacklist = [x.strip() for x in config['leveling_role_blacklist'].split(',')]
            for role in member.roles:
                if str(role.id) in role_blacklist:
                    return False

        # Check whitelist/blacklist
        channel_id = str(channel_id)
        if config.get('leveling_whitelist'):
            whitelisted = [x.strip() for x in config['leveling_whitelist'].split(',')]
            if channel_id not in whitelisted:
                return False

        if config.get('leveling_blacklist'):
            blacklisted = [x.strip() for x in config['leveling_blacklist'].split(',')]
            if channel_id in blacklisted:
                return False

        # Check cooldown
        import time
        current_time = time.time()
        if member.id in self.cooldowns:
            if current_time - self.cooldowns[member.id] < config.get('xp_cooldown', 60):
                return False

        self.cooldowns[member.id] = current_time
        return True

    def calculate_xp_gain(self, member, config):
        import random
        base_xp = random.randint(int(config.get('xp_min', 15)), int(config.get('xp_max', 25)))
        multipliers = self.get_multipliers(str(member.guild.id))
        highest_multiplier = 1.0
        for role in member.roles:
            if str(role.id) in multipliers:
                highest_multiplier = max(highest_multiplier, multipliers[str(role.id)])

        # Apply global active XP drop
        guild_id_str = str(member.guild.id)
        if guild_id_str in self.active_drops:
            drop_data = self.active_drops[guild_id_str]
            now = datetime.datetime.now().timestamp()
            if now < drop_data['expires_at']:
                highest_multiplier *= drop_data['multiplier']
            else:
                del self.active_drops[guild_id_str]

        return int(base_xp * highest_multiplier)

    async def grant_xp(self, member, xp_gain, config, fallback_channel=None):
        # We cache the gain locally
        if member.id not in self.xp_cache:
            self.xp_cache[member.id] = 0
        self.xp_cache[member.id] += xp_gain

        # But we must instantly evaluate level-ups to keep the UI responsive.
        # So we calculate their total projected XP right now.
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT xp, level FROM leveling_users WHERE user_id = ?", (member.id,))
        row = cursor.fetchone()

        if row:
            current_db_xp, current_level = row
        else:
            current_db_xp, current_level = 0, 0

        projected_total_xp = current_db_xp + self.xp_cache[member.id]

        correct_level = self.get_level_from_xp(projected_total_xp)
        if correct_level > current_level:
            # Level up! They might have skipped multiple levels, so we use correct_level.
            cursor.execute("INSERT OR REPLACE INTO leveling_users (user_id, xp, level) VALUES (?, ?, ?)", (member.id, projected_total_xp, correct_level))
            self.bot.db_conn.commit()
            self.xp_cache[member.id] = 0 # reset cache since we saved it

            await self.process_level_up(member, correct_level, config, fallback_channel)

    @tasks.loop(minutes=3.0)
    async def level_audit_loop(self):
        try:
            cursor = self.bot.db_conn.cursor()
            cursor.execute("SELECT user_id, xp, level FROM leveling_users")
            users = cursor.fetchall()

            for user_id, xp, current_level in users:
                correct_level = self.get_level_from_xp(xp)
                if correct_level != current_level:
                    # They are desynced (either too low or too high). Correct it.
                    cursor.execute("UPDATE leveling_users SET level = ? WHERE user_id = ?", (correct_level, user_id))
                    self.bot.db_conn.commit()

                    user_id_int = int(user_id)
                    member = None
                    for guild in self.bot.guilds:
                        member = guild.get_member(user_id_int)
                        if member:
                            break

                    if member:
                        config = self.get_xp_config(str(member.guild.id))
                        await self.process_level_up(member, correct_level, config, fallback_channel=None)
        except Exception as e:
            print(f"Exception in level_audit_loop: {e}")

    @level_audit_loop.before_loop
    async def before_level_audit_loop(self):
        await self.bot.wait_until_ready()

    @level_audit_loop.error
    async def level_audit_loop_error(self, error):
        print(f"level_audit_loop crashed with error: {error}")
        self.level_audit_loop.restart()

    @tasks.loop(minutes=2.0)
    async def flush_cache(self):
        try:
            await self.sync_cache_to_db()
        except Exception as e:
            print(f"Exception in flush_cache loop: {e}")

    @flush_cache.error
    async def flush_cache_error(self, error):
        print(f"flush_cache loop crashed with error: {error}")
        self.flush_cache.restart()

    async def sync_cache_to_db(self):
        if not self.xp_cache: return
        cursor = self.bot.db_conn.cursor()
        for user_id, pending_xp in list(self.xp_cache.items()):
            if pending_xp <= 0: continue

            cursor.execute("SELECT xp FROM leveling_users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                cursor.execute("UPDATE leveling_users SET xp = xp + ? WHERE user_id = ?", (pending_xp, user_id))
            else:
                cursor.execute("INSERT INTO leveling_users (user_id, xp, level) VALUES (?, ?, ?)", (user_id, pending_xp, 0))

            self.xp_cache[user_id] = 0
        self.bot.db_conn.commit()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        config = self.get_xp_config(str(message.guild.id) if message and getattr(message, "guild", None) else None)

        if len(message.content) < config['leveling_min_length']:
            return

        if not await self.check_permissions_and_cooldown(message.author, message.channel.id, config):
            return

        xp_gain = self.calculate_xp_gain(message.author, config)
        await self.grant_xp(message.author, xp_gain, config, message.channel)

    @tasks.loop(minutes=5.0)
    async def voice_xp_loop(self):
        try:
            for guild in self.bot.guilds:
                config = self.get_xp_config(str(guild.id))
                for vc in guild.voice_channels:
                    try:
                        valid_members = [m for m in vc.members if not m.bot and not m.voice.self_deaf and not m.voice.deaf]
                        if len(valid_members) < 2:
                            continue

                        for member in valid_members:
                            if not await self.check_permissions_and_cooldown(member, vc.id, config):
                                continue
                            xp_gain = self.calculate_xp_gain(member, config)
                            await self.grant_xp(member, xp_gain, config)
                    except Exception as e:
                        print(f"Exception in voice_xp_loop for vc {vc.id}: {e}")
        except Exception as e:
            print(f"Exception in voice_xp_loop outer: {e}")

    @voice_xp_loop.before_loop
    async def before_voice_xp_loop(self):
        await self.bot.wait_until_ready()

    @voice_xp_loop.error
    async def voice_xp_loop_error(self, error):
        print(f"voice_xp_loop crashed with error: {error}")
        self.voice_xp_loop.restart()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return

        # Starting voice session
        if before.channel is None and after.channel is not None:
            pass # We could track join times here if we want to run a loop, but let's implement a simpler approach

        # We will handle voice XP passively using a background task in step 3.
        # But for now, we'll just prep the level up logic handler.

    async def process_level_up(self, member, new_level, config, fallback_channel=None):
        # Apply Role Rewards
        rewards = self.get_rewards(str(member.guild.id))
        roles_to_add = []
        roles_to_remove = []

        # Sort rewards so highest level is last
        rewards.sort(key=lambda x: x[0])
        highest_earned_role = None

        for r_level, r_role_id in rewards:
            role = member.guild.get_role(int(r_role_id))
            if role:
                if new_level >= r_level:
                    roles_to_add.append(role)
                    highest_earned_role = role
                else:
                    roles_to_remove.append(role)

        if config['leveling_role_stacking'] == 'replace':
            if highest_earned_role:
                roles_to_add = [highest_earned_role]
            else:
                roles_to_add = []

            # Remove all other leveling roles they have (or all if they lost everything via demotion)
            for r_level, r_role_id in rewards:
                r = member.guild.get_role(int(r_role_id))
                if r and r != highest_earned_role and r in member.roles:
                    roles_to_remove.append(r)

        try:
            if roles_to_remove: await member.remove_roles(*roles_to_remove, reason=f"Level {new_level} Role Replacement")
            if roles_to_add: await member.add_roles(*[r for r in roles_to_add if r not in member.roles], reason=f"Level {new_level} Reward")
        except Exception as e:
            print(f"Failed to manage role rewards: {e}")

        # Announce
        announce_channel_opt = config['leveling_announcement_channel']
        custom_message = config['leveling_custom_message'].format(
            user=member.mention,
            level=new_level,
            role=highest_earned_role.name if highest_earned_role else "None"
        )

        try:
            if announce_channel_opt == 'dm':
                await member.send(custom_message)
            elif announce_channel_opt == 'current' and fallback_channel:
                await fallback_channel.send(custom_message)
            elif announce_channel_opt.isdigit():
                chan = member.guild.get_channel(int(announce_channel_opt))
                if chan: await chan.send(custom_message)
        except:
            pass

    @commands.hybrid_command(name="rank", description="Check your current level and XP.")
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author

        # Flush their specific cache to ensure accurate stats
        if member.id in self.xp_cache and self.xp_cache[member.id] > 0:
            cursor = self.bot.db_conn.cursor()
            cursor.execute("SELECT xp FROM leveling_users WHERE user_id = ?", (member.id,))
            row = cursor.fetchone()
            if row:
                cursor.execute("UPDATE leveling_users SET xp = xp + ? WHERE user_id = ?", (self.xp_cache[member.id], member.id))
            else:
                cursor.execute("INSERT INTO leveling_users (user_id, xp, level) VALUES (?, ?, ?)", (member.id, self.xp_cache[member.id], 0))
            self.bot.db_conn.commit()
            self.xp_cache[member.id] = 0

        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT xp, level FROM leveling_users WHERE user_id = ?", (member.id,))
        row = cursor.fetchone()

        if not row:
            return await ctx.send(f"{member.display_name} has not earned any XP yet.", ephemeral=True)

        xp, level = row
        next_xp = self.calc_xp_for_level(level)

        cursor.execute("SELECT COUNT(*) FROM leveling_users WHERE xp > ?", (xp,))
        rank_pos = cursor.fetchone()[0] + 1

        # Generate Rank Card Image
        try:
            # Base Canvas
            bg = Image.new('RGB', (800, 250), color=(43, 45, 49))
            draw = ImageDraw.Draw(bg)

            # Draw Progress Bar Background
            bar_x = 230
            bar_y = 170
            bar_width = 520
            bar_height = 30
            draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], radius=15, fill=(30, 31, 34))

            # Draw Progress Bar Fill
            prev_xp = self.calc_xp_for_level(level - 1) if level > 0 else 0
            current_level_xp = xp - prev_xp
            total_level_xp = next_xp - prev_xp

            progress = max(0.01, min(1.0, current_level_xp / max(1, total_level_xp)))
            fill_width = int(bar_width * progress)
            draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_width, bar_y + bar_height], radius=15, fill=(88, 101, 242))

            # Fetch Avatar
            async with aiohttp.ClientSession() as session:
                async with session.get(member.display_avatar.with_size(128).url) as resp:
                    avatar_data = await resp.read()
                    avatar_img = Image.open(io.BytesIO(avatar_data)).convert("RGBA")
                    avatar_img = avatar_img.resize((150, 150))

                    # Create circular mask for avatar
                    mask = Image.new("L", (150, 150), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse((0, 0, 150, 150), fill=255)

                    bg.paste(avatar_img, (40, 50), mask)

            # Try to load fonts
            try:
                # Use default PIL font if no ttf available
                font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
                font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 25)
            except IOError:
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()

            # Draw Text
            draw.text((230, 60), member.display_name, font=font_large, fill=(255, 255, 255))
            draw.text((230, 110), f"Rank #{rank_pos}  |  Level {level}", font=font_medium, fill=(185, 187, 190))
            draw.text((600, 120), f"{xp:,} / {next_xp:,} XP", font=font_small, fill=(255, 255, 255))

            # Save to buffer
            buffer = io.BytesIO()
            bg.save(buffer, "PNG")
            buffer.seek(0)
            file = discord.File(buffer, filename="rank.png")

            await ctx.send(file=file)

        except Exception as e:
            print(f"Failed to generate rank card: {e}")
            # Fallback to embed
            embed = discord.Embed(title=f"Rank: {member.display_name}", color=discord.Color.from_str("#2B2D31"))
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="Rank", value=f"#{rank_pos}", inline=True)
            embed.add_field(name="Level", value=str(level), inline=True)
            embed.add_field(name="XP", value=f"{xp} / {next_xp}", inline=True)
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard", description="View the server's most active members.")
    async def leaderboard(self, ctx):
        await self.sync_cache_to_db()
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT user_id, xp, level FROM leveling_users ORDER BY xp DESC LIMIT 10")
        rows = cursor.fetchall()

        if not rows:
            return await ctx.send("The leaderboard is currently empty.", ephemeral=True)

        embed = discord.Embed(title="🏆 Server Leaderboard", color=discord.Color.from_str("#2B2D31"))

        desc = ""
        for i, row in enumerate(rows):
            user_id, xp, level = row
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"Unknown User ({user_id})"
            desc += f"**{i+1}.** {name} — **Level {level}** ({xp} XP)\n"

        embed.description = desc
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rewards", description="View all unlockable role rewards.")
    async def rewards_list(self, ctx):
        rewards = self.get_rewards(str(member.guild.id))
        if not rewards:
            return await ctx.send("There are no role rewards configured for this server yet.", ephemeral=True)

        embed = discord.Embed(title="🎁 Unlockable Role Rewards", color=discord.Color.from_str("#2B2D31"))
        desc = ""
        for r_level, r_role_id in sorted(rewards, key=lambda x: x[0]):
            role = ctx.guild.get_role(int(r_role_id))
            if role:
                desc += f"**Level {r_level}:** {role.mention}\n"

        if not desc:
            desc = "All configured roles have been deleted from the server."

        embed.description = desc
        await ctx.send(embed=embed)

    # --- ADMIN COMMANDS ---

    @commands.hybrid_group(name="xp", description="Manage user XP (Admin only).")
    @commands.has_permissions(administrator=True)
    async def xp_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid subcommand. Use `/xp add`, `/xp remove`, or `/xp set`.")

    @xp_group.command(name="add", description="Add XP to a user.")
    @commands.has_permissions(administrator=True)
    async def xp_add(self, ctx, member: discord.Member, amount: int):
        if amount <= 0: return await ctx.send("Amount must be positive.", ephemeral=True)
        await self.sync_cache_to_db()
        config = self.get_xp_config(str(ctx.guild.id) if ctx.guild else None)
        cursor = self.bot.db_conn.cursor()

        cursor.execute("SELECT xp FROM leveling_users WHERE user_id = ?", (member.id,))
        row = cursor.fetchone()

        if row:
            new_xp = row[0] + amount
            cursor.execute("UPDATE leveling_users SET xp = ? WHERE user_id = ?", (new_xp, member.id))
        else:
            new_xp = amount
            cursor.execute("INSERT INTO leveling_users (user_id, xp, level) VALUES (?, ?, 0)", (member.id, new_xp))

        self.bot.db_conn.commit()
        await ctx.send(f"Added {amount} XP to {member.mention}.")

        # Check level up
        cursor.execute("SELECT level FROM leveling_users WHERE user_id = ?", (member.id,))
        current_level = cursor.fetchone()[0]

        # Calculate what their level SHOULD be based on new_xp
        expected_level = 0
        while new_xp >= self.calc_xp_for_level(expected_level):
            expected_level += 1

        if expected_level > current_level:
            cursor.execute("UPDATE leveling_users SET level = ? WHERE user_id = ?", (expected_level, member.id))
            self.bot.db_conn.commit()
            await self.process_level_up(member, expected_level, config, ctx.channel)


    @xp_group.command(name="remove", description="Remove XP from a user.")
    @commands.has_permissions(administrator=True)
    async def xp_remove(self, ctx, member: discord.Member, amount: int):
        if amount <= 0: return await ctx.send("Amount must be positive.", ephemeral=True)
        await self.sync_cache_to_db()
        cursor = self.bot.db_conn.cursor()

        cursor.execute("SELECT xp FROM leveling_users WHERE user_id = ?", (member.id,))
        row = cursor.fetchone()

        if not row:
            return await ctx.send(f"{member.display_name} has no XP.", ephemeral=True)

        new_xp = max(0, row[0] - amount)

        # Calculate downgraded level
        expected_level = 0
        while new_xp >= self.calc_xp_for_level(expected_level):
            expected_level += 1

        cursor.execute("UPDATE leveling_users SET xp = ?, level = ? WHERE user_id = ?", (new_xp, expected_level, member.id))
        self.bot.db_conn.commit()

        await ctx.send(f"Removed {amount} XP from {member.mention}. They are now Level {expected_level} with {new_xp} XP.")

    @xp_group.command(name="set", description="Set a user's exact XP.")
    @commands.has_permissions(administrator=True)
    async def xp_set(self, ctx, member: discord.Member, amount: int):
        if amount < 0: return await ctx.send("Amount must be 0 or positive.", ephemeral=True)
        await self.sync_cache_to_db()
        config = self.get_xp_config(str(ctx.guild.id) if ctx.guild else None)
        cursor = self.bot.db_conn.cursor()

        expected_level = 0
        while amount >= self.calc_xp_for_level(expected_level):
            expected_level += 1

        cursor.execute("INSERT OR REPLACE INTO leveling_users (user_id, xp, level) VALUES (?, ?, ?)", (member.id, amount, expected_level))
        self.bot.db_conn.commit()

        await ctx.send(f"Set {member.mention}'s XP to {amount} (Level {expected_level}).")
        await self.process_level_up(member, expected_level, config, ctx.channel)


    @commands.hybrid_group(name="level", description="Manage user levels (Admin only).")
    @commands.has_permissions(administrator=True)
    async def level_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid subcommand. Use `/level set` or `/level reset`.")

    @level_group.command(name="set", description="Set a user's level directly.")
    @commands.has_permissions(administrator=True)
    async def level_set(self, ctx, member: discord.Member, level: int):
        if level < 0: return await ctx.send("Level must be 0 or positive.", ephemeral=True)
        await self.sync_cache_to_db()
        config = self.get_xp_config(str(ctx.guild.id) if ctx.guild else None)
        cursor = self.bot.db_conn.cursor()

        # Give them the minimum XP for that level
        new_xp = 0
        if level > 0:
            new_xp = self.calc_xp_for_level(level - 1)

        cursor.execute("INSERT OR REPLACE INTO leveling_users (user_id, xp, level) VALUES (?, ?, ?)", (member.id, new_xp, level))
        self.bot.db_conn.commit()

        await ctx.send(f"Set {member.mention} directly to Level {level}.")
        await self.process_level_up(member, level, config, ctx.channel)

    @level_group.command(name="reset", description="Reset a user's XP/Level, or reset the entire server.")
    @commands.has_permissions(administrator=True)
    async def level_reset(self, ctx, member: discord.Member = None, server_wide: bool = False):
        await self.sync_cache_to_db()
        cursor = self.bot.db_conn.cursor()

        if server_wide:
            cursor.execute("DELETE FROM leveling_users")
            self.bot.db_conn.commit()
            await ctx.send("🚨 The entire server leaderboard and all XP has been completely reset.")
        elif member:
            cursor.execute("DELETE FROM leveling_users WHERE user_id = ?", (member.id,))
            self.bot.db_conn.commit()
            await ctx.send(f"{member.mention}'s XP and Level have been completely reset to 0.")
        else:
            await ctx.send("You must specify a member to reset, or set `server_wide` to True.", ephemeral=True)


    @commands.hybrid_command(name="xpdrop", description="[ADMIN] Trigger a global XP multiplier event")
    @commands.has_permissions(administrator=True)
    async def xpdrop(self, ctx: commands.Context, multiplier: float, duration_hours: float):
        if multiplier <= 1.0 or multiplier > 10.0:
            return await ctx.send("Multiplier must be between 1.1 and 10.0", ephemeral=True)
        if duration_hours <= 0 or duration_hours > 72:
            return await ctx.send("Duration must be between 0.1 and 72 hours.", ephemeral=True)

        expires_at = datetime.datetime.now().timestamp() + (duration_hours * 3600)
        self.active_drops[str(ctx.guild.id)] = {'multiplier': multiplier, 'expires_at': expires_at}

        embed = discord.Embed(title="🎁 GLOBAL XP DROP 🎁", description=f"An admin has activated a global **{multiplier}x XP Boost** for the entire server!", color=discord.Color.gold())
        embed.add_field(name="Duration", value=f"Ends <t:{int(expires_at)}:R>")
        await ctx.send(embed=embed)

    def get_rewards(self, guild_id):
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT level, role_id FROM leveling_rewards WHERE guild_id = ? ORDER BY level ASC", (str(guild_id),))
        return [{"level": row[0], "role_id": row[1]} for row in cursor.fetchall()]

    def get_multipliers(self, guild_id):
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT role_id, multiplier FROM leveling_multipliers WHERE guild_id = ?", (str(guild_id),))
        return {row[0]: float(row[1]) for row in cursor.fetchall()}

    def calc_xp_for_level(self, level: int) -> int:
        if level <= 0: return 0
        return 5 * (level ** 2) + 50 * level + 100

    def get_level_from_xp(self, xp: int) -> int:
        level = 0
        while xp >= self.calc_xp_for_level(level + 1):
            level += 1
        return level


    def get_level_from_xp(self, xp: int) -> int:
        level = 0
        while xp >= self.calc_xp_for_level(level + 1):
            level += 1
        return level


async def setup(bot):
    await bot.add_cog(Leveling(bot))
