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

async def setup(bot):
    await bot.add_cog(AutomodCog(bot))
