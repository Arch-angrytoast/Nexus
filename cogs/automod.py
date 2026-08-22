import discord
from discord.ext import commands
import re
import datetime
from collections import defaultdict

# --- Configuration & Regex ---
# Zero-width spaces & combining characters
ZALGO_REGEX = re.compile(r'[​-‍﻿̀-ͯ]')
INVITE_REGEX = re.compile(r'(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)[a-zA-Z0-9]+', re.IGNORECASE)
# A simple heuristic for non-english text: Look for non-ASCII alphanumeric characters
# Not perfect, but a lightweight way to flag heavy usage of other alphabets (Cyrillic, Arabic, CJK, etc)
NON_ENGLISH_REGEX = re.compile(r'[^\x00-\x7F]+')
BOT_PREFIXES = ('!', '?', '-', '/', '.')

class AutomodCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # For spam tracking: maps user_id to list of message timestamps
        self.spam_tracker = defaultdict(list)
        # For duplicate tracking: maps user_id to dict { 'content': str, 'timestamp': float, 'count': int }
        self.duplicate_tracker = defaultdict(dict)
        # For voice hopping tracking: maps user_id to list of join/switch timestamps
        self.voice_tracker = defaultdict(list)

    def get_config(self, guild_id, key: str):
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT value FROM server_config WHERE guild_id = ? AND key = ?", (str(guild_id), key))
        row = cursor.fetchone()
        return row[0] if row else None

    async def apply_escalation(self, guild: discord.Guild, member: discord.Member, total_points: int):
        bot_member = guild.me
        if bot_member.top_role <= member.top_role or member.id == guild.owner_id:
            return # Can't punish someone higher/equal to us

        try:
            if total_points >= 100:
                await member.ban(reason=f"Automod: Reached {total_points} warning points.")
                return "Banned"
            elif total_points >= 80:
                await member.kick(reason=f"Automod: Reached {total_points} warning points.")
                return "Kicked"
            elif total_points >= 60:
                await member.timeout(datetime.timedelta(hours=24), reason=f"Automod: Reached {total_points} warning points.")
                return "Timed out for 24h"
            elif total_points >= 40:
                await member.timeout(datetime.timedelta(hours=12), reason=f"Automod: Reached {total_points} warning points.")
                return "Timed out for 12h"
            elif total_points >= 20:
                await member.timeout(datetime.timedelta(hours=1), reason=f"Automod: Reached {total_points} warning points.")
                return "Timed out for 1h"
        except discord.Forbidden:
            return "Failed (Missing Permissions)"
        return "Warned"

    async def issue_warning(self, message: discord.Message, reason: str, points: int):
        await self.process_warning(message.guild, message.author, message.channel, reason, points)
        try:
            await message.delete()
        except Exception:
            pass

    async def process_warning(self, guild: discord.Guild, member: discord.Member, channel, reason: str, points: int):
        # 1. Save to DB
        utc_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor = self.bot.db_conn.cursor()
        cursor.execute(
            "INSERT INTO warnings (user_id, mod_id, reason, points, timestamp) VALUES (?, ?, ?, ?, ?)",
            (member.id, self.bot.user.id, f"[AUTOMOD] {reason}", points, utc_now)
        )
        self.bot.db_conn.commit()

        # 2. Calculate total points in last 30 days
        thirty_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat()
        cursor.execute(
            "SELECT SUM(points) FROM warnings WHERE user_id = ? AND timestamp > ?",
            (member.id, thirty_days_ago)
        )
        total_points = cursor.fetchone()[0] or 0

        # 3. Apply Automod Punishment
        action_taken = await self.apply_escalation(guild, member, total_points)

        # 3.5 Toxicity XP Freeze
        try:
            leveling_cog = self.bot.get_cog("Leveling")
            if leveling_cog:
                # Freeze XP for 2 hours per warning point they have total
                freeze_hours = min(48, max(2, total_points * 2))
                expires = datetime.datetime.now().timestamp() + (freeze_hours * 3600)
                leveling_cog.xp_freezes[member.id] = expires
        except Exception:
            pass

        # 4. Notify user in channel
        if channel:
            try:
                from . import embed_factory
                content = f"**{member.mention}**, you violated a server rule.\n\n"
                content += f"**Reason:** {reason}\n"
                content += f"**Points:** +{points}\n"
                content += f"**Action Taken:** {action_taken}\n"
                embed = embed_factory.create_clean_embed("⚠️ Warning Issued", content, footer_text=f"Total Points: {total_points}/100")
                await channel.send(embed=embed, delete_after=15)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Ignore admins/mods
        if message.author.guild_permissions.manage_messages:
            return

        content_lower = message.content.lower()
        general_channel_id = self.get_config(str(message.guild.id), "general_channel")
        spam_channel_id = self.get_config(str(message.guild.id), "spam_channel")

        is_general = str(message.channel.id) == str(general_channel_id)
        is_spam = str(message.channel.id) == str(spam_channel_id)

        def is_enabled(key: str, gid: str = None) -> bool:
            val = self.get_config(gid or str(message.guild.id), key)
            return val is None or val == "1" # Default to True

        # --- File Extension Whitelist (Media Defense) ---
        if message.attachments:
            forbidden_extensions = ('.exe', '.bat', '.scr', '.vbs', '.msi', '.cmd', '.js', '.jar')
            for attachment in message.attachments:
                if attachment.filename.lower().endswith(forbidden_extensions):
                    await self.issue_warning(message, f"Uploaded dangerous file ({attachment.filename})", 10)
                    return

        # --- Granular Throttles ---
        # --- Honeypot & Deception Traps ---
        if hasattr(message.channel, "topic") and message.channel.topic and "HONEYPOT_CHANNEL_DO_NOT_POST" in message.channel.topic:
            try:
                await message.author.ban(reason="AutoMod: Triggered Honeypot Trap (Self-Bot/Scraper)")
                await self.process_warning(message.guild, message.author, None, "Triggered Honeypot Trap", 100)
            except discord.Forbidden:
                pass
            return

        # 1. Caps Lock
        if len(message.content) > 15:
            alpha_chars = [c for c in message.content if c.isalpha()]
            if alpha_chars:
                upper_chars = [c for c in alpha_chars if c.isupper()]
                if (len(upper_chars) / len(alpha_chars)) > 0.7:
                    await self.issue_warning(message, "Excessive Caps Lock (>70%)", 1)
                    return

        # 2. Emoji & Sticker Flood
        custom_emojis = len(CUSTOM_EMOJI_REGEX.findall(message.content))
        unicode_emojis = len(UNICODE_EMOJI_REGEX.findall(message.content))
        if custom_emojis + unicode_emojis > 10 or len(message.stickers) > 2:
            await self.issue_warning(message, "Emoji / Sticker Flood", 2)
            return

        # 3. Spoiler Abuse
        if message.content.count('||') > 6: # More than 3 spoiler blocks (6 pipes)
            await self.issue_warning(message, "Spoiler Tag Abuse", 1)
            return

        # Zalgo/Unicode Normalizer
        if ZALGO_REGEX.search(message.content):
            # Strip zalgo to check the raw content
            clean_text = ZALGO_REGEX.sub('', message.content)
            if len(clean_text) < len(message.content) * 0.5 and len(message.content) > 10:
                await self.issue_warning(message, "Zalgo / Invisible Text Spam", 2)
                return
            message.content = clean_text # Use cleaned content for further checks

        # Mentions Limiter
        if len(message.raw_mentions) + len(message.raw_role_mentions) > 5:
            await self.issue_warning(message, "Mass Mentions (More than 5)", 5)
            return

        # 1. Check Invites (Rule 3)
        if is_enabled("filter_links") and INVITE_REGEX.search(content_lower):
            await self.issue_warning(message, "Posting Unauthorized Invites", 3)
            return



        # 3. Check English-Only (Rule 3)
        if is_enabled("filter_english") and is_general:
            clean_content = re.sub(r'<:[a-zA-Z0-9_]+:[0-9]+>|<@!?[0-9]+>|<#[0-9]+>|[\s\.,!\?\'\"]', '', message.content)
            if clean_content:
                non_english_chars = NON_ENGLISH_REGEX.findall(clean_content)
                non_english_count = sum(len(match) for match in non_english_chars)
                if (non_english_count / len(clean_content)) > 0.3:
                    await self.issue_warning(message, "Non-English text in general channel", 1)
                    return

        # 4. Bot Command Enforcement (Rule 4)
        if is_enabled("filter_commands") and is_general:
            if message.content.startswith(BOT_PREFIXES):
                await self.issue_warning(message, "Using bot commands in general channel", 1)
                return

        # 5. Velocity & Anti-Spam (Rule 3)
        if is_enabled("filter_spam") and not is_spam:
            now = datetime.datetime.now().timestamp()

            # --- Fast Paste / Macro Suppression ---
            if len(message.content) > 300:
                # If they send a massive message extremely quickly after their last one, it's a macro/paste
                user_times = self.spam_tracker.get(message.author.id, [])
                if user_times and (now - user_times[-1]) < 0.6:
                    await self.issue_warning(message, "Fast-Paste / Macro Spam", 4)
                    return

            # --- Leaky-Bucket Rate Limiting ---
            timestamps = self.spam_tracker[message.author.id]
            timestamps = [t for t in timestamps if now - t < 5]
            timestamps.append(now)
            self.spam_tracker[message.author.id] = timestamps

            if len(timestamps) >= 5:
                self.spam_tracker[message.author.id] = []
                await self.issue_warning(message, "Rapid-fire Spam", 2)
                return

            # --- Cross-Channel Duplicate Detection ---
            if len(message.content) > 10:
                dup_data = self.duplicate_tracker[message.author.id]
                if dup_data.get('content') == content_lower and (now - dup_data.get('timestamp', 0)) < 15:
                    dup_data['count'] = dup_data.get('count', 1) + 1
                    dup_data['timestamp'] = now
                    if dup_data['count'] >= 3:
                        dup_data['count'] = 0
                        await self.issue_warning(message, "Cross-Channel Duplicate Spam", 3)
                        return
                else:
                    self.duplicate_tracker[message.author.id] = {'content': content_lower, 'timestamp': now, 'count': 1}

    @commands.Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModAction):
        # Only process block actions from our specific rule to avoid double counting
        if execution.action.type != discord.AutoModRuleActionType.block_message:
            return

        # We don't have the rule name directly, but we can verify it was a custom keyword trigger
        # We can also check if the rule_id matches if we cached it, but for now we just verify it's a keyword block
        # execution doesn't have rule.name, it might have rule_id
        # Let's just process it if it's a keyword block


        # Discord has natively blocked it, so we just process the points!
        guild = execution.member.guild if execution.member else None
        if not guild or not execution.member:
            return

        channel = guild.get_channel(execution.channel_id)

        # The word they got caught using
        trigger_word = execution.matched_keyword or "a banned word"
        reason = f"Using Banned Words ({trigger_word})"

        await self.process_warning(guild, execution.member, channel, reason, 4)

    @commands.hybrid_command(name="setup-honeypot", description="[ADMIN] Create an invisible honeypot channel to trap self-bots")
    @commands.has_permissions(administrator=True)
    async def setup_honeypot(self, ctx: commands.Context):
        guild = ctx.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=False)
        }

        try:
            channel = await guild.create_text_channel(
                name="secret-staff-logs", # Enticing name for scrapers
                overwrites=overwrites,
                topic="HONEYPOT_CHANNEL_DO_NOT_POST",
                reason="AutoMod Honeypot Creation"
            )
            await ctx.send(f"✅ Honeypot channel {channel.mention} created! It is invisible to regular users. Any self-bot or user who posts here will be permanently banned.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ I lack permissions to create channels.", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot: return

        # We only care about joining or switching channels
        if after.channel is not None and (before.channel is None or before.channel != after.channel):
            now = datetime.datetime.now().timestamp()
            timestamps = self.voice_tracker[member.id]
            timestamps = [t for t in timestamps if now - t < 10] # Track over 10 seconds
            timestamps.append(now)
            self.voice_tracker[member.id] = timestamps

            if len(timestamps) >= 5: # 5 hops/joins in 10 seconds
                self.voice_tracker[member.id] = []
                try:
                    await member.edit(mute=True, reason="AutoMod: Voice Channel Hopping Spam")
                    # Optionally assign points
                    await self.process_warning(member.guild, member, None, "Voice Channel Hopping Spam", 3)
                except discord.Forbidden:
                    pass

async def setup(bot):
    await bot.add_cog(AutomodCog(bot))
