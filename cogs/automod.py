import discord
from discord.ext import commands
import re
import datetime
from collections import defaultdict

# --- Configuration & Regex ---
INVITE_REGEX = re.compile(r'(discord\.gg/|discord\.com/invite/)[a-zA-Z0-9]+', re.IGNORECASE)
# A simple heuristic for non-english text: Look for non-ASCII alphanumeric characters
# Not perfect, but a lightweight way to flag heavy usage of other alphabets (Cyrillic, Arabic, CJK, etc)
NON_ENGLISH_REGEX = re.compile(r'[^\x00-\x7F]+')
BOT_PREFIXES = ('!', '?', '-', '/', '.')

class AutomodCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # For spam tracking: maps user_id to list of message timestamps
        self.spam_tracker = defaultdict(list)

    def get_config(self, key: str):
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT value FROM server_config WHERE key = ?", (key,))
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
        # 1. Save to DB
        utc_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor = self.bot.db_conn.cursor()
        cursor.execute(
            "INSERT INTO warnings (user_id, mod_id, reason, points, timestamp) VALUES (?, ?, ?, ?, ?)",
            (message.author.id, self.bot.user.id, f"[AUTOMOD] {reason}", points, utc_now)
        )
        self.bot.db_conn.commit()

        # 2. Delete the offending message
        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass

        # 3. Calculate total points in last 30 days
        thirty_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat()
        cursor.execute(
            "SELECT SUM(points) FROM warnings WHERE user_id = ? AND timestamp > ?",
            (message.author.id, thirty_days_ago)
        )
        total_points = cursor.fetchone()[0] or 0

        # 4. Apply Automod Punishment
        action_taken = await self.apply_escalation(message.guild, message.author, total_points)

        # 5. Notify user in channel
        try:
            await message.channel.send(f"⚠️ {message.author.mention}, you have been warned for **{reason}** (+{points} pts). Total: {total_points} pts. Action: {action_taken}", delete_after=10)
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Ignore admins/mods
        if message.author.guild_permissions.manage_messages:
            return

        content_lower = message.content.lower()
        general_channel_id = self.get_config("general_channel")
        spam_channel_id = self.get_config("spam_channel")

        is_general = str(message.channel.id) == str(general_channel_id)
        is_spam = str(message.channel.id) == str(spam_channel_id)

        def is_enabled(key: str) -> bool:
            val = self.get_config(key)
            return val is None or val == "1" # Default to True

        # 1. Check Invites (Rule 3)
        if is_enabled("filter_links") and INVITE_REGEX.search(content_lower):
            await self.issue_warning(message, "Posting Unauthorized Invites", 3)
            return

        # 2. Check Banned Words (Rule 2 filter bypassing)
        if is_enabled("filter_words"):
            banned_words_str = self.get_config("banned_words")
            if banned_words_str:
                banned_words_list = [w.strip() for w in banned_words_str.split(',') if w.strip()]
                if any(word in content_lower for word in banned_words_list):
                    await self.issue_warning(message, "Using Banned Words", 4)
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

        # 5. Spam Control (Rule 3)
        if is_enabled("filter_spam") and not is_spam:
            now = datetime.datetime.now().timestamp()
            timestamps = self.spam_tracker[message.author.id]
            timestamps = [t for t in timestamps if now - t < 5]
            timestamps.append(now)
            self.spam_tracker[message.author.id] = timestamps

            if len(timestamps) >= 5:
                self.spam_tracker[message.author.id] = []
                await self.issue_warning(message, "Spamming messages", 2)
                return

async def setup(bot):
    await bot.add_cog(AutomodCog(bot))
