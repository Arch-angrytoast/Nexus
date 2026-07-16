import discord
from discord.ext import commands
import datetime
from collections import defaultdict
import os

class AntiNukeTracker:
    def __init__(self, limit=5, per_seconds=10):
        self.limit = limit
        self.per_seconds = per_seconds
        # Maps user_id -> list of timestamps
        self._records = defaultdict(list)

    def add_action_and_check(self, user_id: int) -> bool:
        """Returns True if the user has exceeded the threshold."""
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()

        # Clean old timestamps
        valid_times = [t for t in self._records[user_id] if now - t <= self.per_seconds]
        valid_times.append(now)
        self._records[user_id] = valid_times

        if len(valid_times) >= self.limit:
            self._records[user_id] = [] # Reset after trigger to prevent double-firing
            return True
        return False

class AntiNukeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Separate trackers to prevent someone getting banned for doing 1 of each (which is normal setup behavior)
        self.ban_tracker = AntiNukeTracker()
        self.kick_tracker = AntiNukeTracker()
        self.channel_tracker = AntiNukeTracker()
        self.role_tracker = AntiNukeTracker()
        self.webhook_tracker = AntiNukeTracker()

    def is_enabled(self) -> bool:
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT value FROM server_config WHERE key = 'antinuke'")
        row = cursor.fetchone()
        return row[0] == "1" if row else True # Default to True

    async def trigger_antinuke(self, guild: discord.Guild, rogue_user: discord.Member | discord.User, reason: str):
        owner_id = str(os.getenv("OWNER_ID"))

        # Security Exception: Do not nuke the server owner, the bot owner, or the bot itself.
        if str(rogue_user.id) == owner_id or rogue_user.id == guild.owner_id or rogue_user.id == self.bot.user.id:
            return

        print(f"[ANTI-NUKE TRIGGERED] {rogue_user} - {reason}")

        # Try to resolve to Member for roles/timeout if not already
        if isinstance(rogue_user, discord.User):
            rogue_member = guild.get_member(rogue_user.id)
        else:
            rogue_member = rogue_user

        # Action 1: Ban the Rogue Admin
        punishment_taken = "None"
        try:
            await guild.ban(rogue_user, reason=f"NEXUS ANTI-NUKE TRIGGERED: {reason}")
            punishment_taken = "Banned"
        except discord.Forbidden:
            # Action 2 Fallback: Quarantine
            if rogue_member:
                try:
                    # Strip all roles
                    await rogue_member.edit(roles=[guild.default_role], reason="NEXUS ANTI-NUKE TRIGGERED: Quarantine")
                    # Maximum timeout (28 days)
                    await rogue_member.timeout(datetime.timedelta(days=28), reason="NEXUS ANTI-NUKE TRIGGERED: Quarantine")
                    punishment_taken = "Roles Stripped & Timed Out (28 days)"
                except discord.Forbidden:
                    punishment_taken = "FAILED - Missing Hierarchy/Permissions"

        # Action 3: Notify Owner
        if owner_id and owner_id != "None" and owner_id != "your_discord_user_id_here":
            try:
                owner_user = await self.bot.fetch_user(int(owner_id))
                from . import embed_factory
                content = f"A severe threat was detected in **{guild.name}**.\n\n"
                content += f"**Rogue User:** {rogue_user.mention} (`{rogue_user.id}`)\n*{rogue_user.name}*\n\n"
                content += f"**Trigger Reason:** {reason}\n\n"
                content += f"**Action Taken:** {punishment_taken}"
                embed = embed_factory.create_clean_embed("🚨 ANTI-NUKE TRIGGERED 🚨", content, color=discord.Color.brand_red())
                await owner_user.send(embed=embed)
            except Exception as e:
                print(f"Failed to DM owner about Anti-Nuke: {e}")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        if not self.is_enabled(): return

        try:
            # We must fetch the audit log to find out WHO did the banning
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
                if entry.target.id == user.id:
                    responsible_user = entry.user
                    if self.ban_tracker.add_action_and_check(responsible_user.id):
                        await self.trigger_antinuke(guild, responsible_user, "Mass Banning Members")
                    break
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not self.is_enabled(): return

        try:
            # Member remove fires for kicks and leaves. We check audit log to see if it was a recent kick.
            # There is a slight race condition here, but checking limit=1 is usually sufficient for antinuke speeds.
            async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
                if entry.target.id == member.id:
                    # Check if the kick happened very recently (within 5 seconds) to avoid false positives from old kicks
                    now = discord.utils.utcnow()
                    if (now - entry.created_at).total_seconds() < 5:
                        responsible_user = entry.user
                        if self.kick_tracker.add_action_and_check(responsible_user.id):
                            await self.trigger_antinuke(member.guild, responsible_user, "Mass Kicking Members")
                    break
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not self.is_enabled(): return

        try:
            async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
                if entry.target.id == channel.id:
                    responsible_user = entry.user
                    if self.channel_tracker.add_action_and_check(responsible_user.id):
                        await self.trigger_antinuke(channel.guild, responsible_user, "Mass Deleting Channels")
                    break
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        if not self.is_enabled(): return

        try:
            async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
                if entry.target.id == role.id:
                    responsible_user = entry.user
                    if self.role_tracker.add_action_and_check(responsible_user.id):
                        await self.trigger_antinuke(role.guild, responsible_user, "Mass Deleting Roles")
                    break
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        if not self.is_enabled(): return

        try:
            # Webhooks update fires when created, modified, or deleted. We only care if created maliciously.
            async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
                # Check if it was recent
                now = discord.utils.utcnow()
                if (now - entry.created_at).total_seconds() < 5:
                    responsible_user = entry.user
                    if self.webhook_tracker.add_action_and_check(responsible_user.id):
                        await self.trigger_antinuke(channel.guild, responsible_user, "Mass Creating Webhooks")
                    break
        except discord.Forbidden:
            pass

async def setup(bot):
    await bot.add_cog(AntiNukeCog(bot))
