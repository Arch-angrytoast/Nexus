import discord
from discord.ext import commands
import sqlite3
from datetime import datetime, timezone
from . import embed_factory
from . import ui_auditlog

class AuditLog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_conn = bot.db_conn

    def get_channel(self, guild_id, log_type):
        cursor = self.db_conn.cursor()
        cursor.execute(f"SELECT {log_type}_channel FROM audit_log_config WHERE guild_id = ?", (str(guild_id),))
        row = cursor.fetchone()
        if row and row[0]:
            return self.bot.get_channel(int(row[0]))
        return None

    # --- MESSAGE LOGS ---
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot:
            return
        channel = self.get_channel(message.guild.id, "message")
        if not channel: return
        embed = embed_factory.create_clean_embed("🗑️ Message Deleted", f"**Author:** {message.author.mention}\n**Channel:** {message.channel.mention}")
        embed.color = discord.Color.red()
        if message.content:
            embed.add_field(name="Content", value=message.content[:1024], inline=False)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        channel = self.get_channel(before.guild.id, "message")
        if not channel: return
        embed = embed_factory.create_clean_embed("✏️ Message Edited", f"**Author:** {before.author.mention}\n**Channel:** {before.channel.mention}\n[Jump to Message]({after.jump_url})")
        embed.color = discord.Color.yellow()
        embed.add_field(name="Before", value=before.content[:1024] or "*Empty*", inline=False)
        embed.add_field(name="After", value=after.content[:1024] or "*Empty*", inline=False)
        await channel.send(embed=embed)

    # --- MEMBER LOGS ---
    @commands.Cog.listener()
    async def on_member_join(self, member):
        channel = self.get_channel(member.guild.id, "member")
        if not channel: return
        embed = embed_factory.create_clean_embed("📥 Member Joined", f"**Member:** {member.mention} (`{member.id}`)")
        embed.color = discord.Color.green()
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        channel = self.get_channel(member.guild.id, "member")
        if not channel: return
        embed = embed_factory.create_clean_embed("📤 Member Left", f"**Member:** {member.mention} (`{member.id}`)")
        embed.color = discord.Color.red()
        embed.set_thumbnail(url=member.display_avatar.url)

        # Check audit logs to see if it was a kick
        try:
            async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
                if entry.target.id == member.id and (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 5:
                    embed.title = "👢 Member Kicked"
                    embed.add_field(name="Moderator", value=entry.user.mention, inline=False)
                    if entry.reason:
                        embed.add_field(name="Reason", value=entry.reason, inline=False)
                    break
        except discord.Forbidden:
            pass

        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        channel = self.get_channel(guild.id, "member")
        if not channel: return
        embed = embed_factory.create_clean_embed("🔨 Member Banned", f"**User:** {user.mention} (`{user.id}`)")
        embed.color = discord.Color.red()

        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
                if entry.target.id == user.id and (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 5:
                    embed.add_field(name="Moderator", value=entry.user.mention, inline=False)
                    if entry.reason:
                        embed.add_field(name="Reason", value=entry.reason, inline=False)
                    break
        except discord.Forbidden:
            pass

        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        channel = self.get_channel(guild.id, "member")
        if not channel: return
        embed = embed_factory.create_clean_embed("🔓 Member Unbanned", f"**User:** {user.mention} (`{user.id}`)")
        embed.color = discord.Color.green()
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        channel = self.get_channel(before.guild.id, "member")
        if not channel: return

        if before.nick != after.nick:
            embed = embed_factory.create_clean_embed("📝 Nickname Changed", f"**Member:** {after.mention}")
            embed.color = discord.Color.yellow()
            embed.add_field(name="Before", value=before.nick or "*None*", inline=False)
            embed.add_field(name="After", value=after.nick or "*None*", inline=False)
            await channel.send(embed=embed)

        if before.roles != after.roles:
            added = [role.mention for role in after.roles if role not in before.roles]
            removed = [role.mention for role in before.roles if role not in after.roles]

            if added or removed:
                embed = embed_factory.create_clean_embed("🏷️ Roles Updated", f"**Member:** {after.mention}")
                embed.color = discord.Color.blue()
                if added:
                    embed.add_field(name="Added", value=", ".join(added), inline=False)
                if removed:
                    embed.add_field(name="Removed", value=", ".join(removed), inline=False)
                await channel.send(embed=embed)

        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until and (not before.timed_out_until or after.timed_out_until > before.timed_out_until):
                embed = embed_factory.create_clean_embed("🔇 Member Timed Out", f"**Member:** {after.mention}")
                embed.color = discord.Color.red()
                embed.add_field(name="Until", value=f"<t:{int(after.timed_out_until.timestamp())}:R>", inline=False)
                await channel.send(embed=embed)
            elif before.timed_out_until and not after.timed_out_until:
                embed = embed_factory.create_clean_embed("🔊 Timeout Removed", f"**Member:** {after.mention}")
                embed.color = discord.Color.green()
                await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_user_update(self, before, after):
        # Only log if they share a guild with the bot that has logging configured, but since it's global user,
        # it's better to just check mutual guilds. For simplicity, we'll iterate mutual guilds.
        # Actually this can be heavy. Let's just track avatar updates for members in on_member_update if possible,
        # but discord.py fires on_user_update for global avatar. We'll do a quick mutual guild check.
        if before.avatar != after.avatar:
            for guild in before.mutual_guilds:
                channel = self.get_channel(guild.id, "member")
                if channel:
                    embed = embed_factory.create_clean_embed("🖼️ Avatar Changed", f"**User:** {after.mention}")
                    embed.color = discord.Color.yellow()
                    if before.avatar:
                        embed.set_thumbnail(url=before.avatar.url)
                    if after.avatar:
                        embed.set_image(url=after.avatar.url)
                    await channel.send(embed=embed)

    # --- SERVER LOGS ---
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        log_channel = self.get_channel(channel.guild.id, "server")
        if not log_channel: return
        embed = embed_factory.create_clean_embed("📁 Channel Created", f"**Channel:** {channel.mention} (`{channel.name}`)")
        embed.color = discord.Color.green()
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        log_channel = self.get_channel(channel.guild.id, "server")
        if not log_channel: return
        embed = embed_factory.create_clean_embed("🗑️ Channel Deleted", f"**Channel:** `{channel.name}`")
        embed.color = discord.Color.red()
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        log_channel = self.get_channel(before.guild.id, "server")
        if not log_channel: return

        embed = embed_factory.create_clean_embed("⚙️ Channel Updated", f"**Channel:** {after.mention}")
        embed.color = discord.Color.yellow()
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` -> `{after.name}`")
        if hasattr(before, 'topic') and before.topic != after.topic:
            changes.append(f"**Topic changed**")

        if changes:
            embed.description += "\n\n" + "\n".join(changes)
            await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        channel = self.get_channel(role.guild.id, "server")
        if not channel: return
        embed = embed_factory.create_clean_embed("🛡️ Role Created", f"**Role:** {role.mention} (`{role.name}`)")
        embed.color = discord.Color.green()
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        channel = self.get_channel(role.guild.id, "server")
        if not channel: return
        embed = embed_factory.create_clean_embed("🗑️ Role Deleted", f"**Role:** `{role.name}`")
        embed.color = discord.Color.red()
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        channel = self.get_channel(before.guild.id, "server")
        if not channel: return

        embed = embed_factory.create_clean_embed("⚙️ Role Updated", f"**Role:** {after.mention}")
        embed.color = discord.Color.yellow()
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` -> `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Color:** `{before.color}` -> `{after.color}`")

        if changes:
            embed.description += "\n\n" + "\n".join(changes)
            await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        channel = self.get_channel(before.id, "server")
        if not channel: return

        embed = embed_factory.create_clean_embed("🏢 Server Updated", f"**Server:** {after.name}")
        embed.color = discord.Color.yellow()
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` -> `{after.name}`")
        if before.icon != after.icon:
            changes.append(f"**Icon Changed**")

        if changes:
            embed.description += "\n\n" + "\n".join(changes)
            await channel.send(embed=embed)

    # --- VOICE LOGS ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        channel = self.get_channel(member.guild.id, "voice")
        if not channel: return

        if not before.channel and after.channel:
            embed = embed_factory.create_clean_embed("🎙️ Voice Joined", f"**Member:** {member.mention}\n**Channel:** {after.channel.mention}")
            embed.color = discord.Color.green()
            await channel.send(embed=embed)
        elif before.channel and not after.channel:
            embed = embed_factory.create_clean_embed("🚪 Voice Left", f"**Member:** {member.mention}\n**Channel:** {before.channel.mention}")
            embed.color = discord.Color.red()
            await channel.send(embed=embed)
        elif before.channel and after.channel and before.channel != after.channel:
            embed = embed_factory.create_clean_embed("🔀 Voice Switched", f"**Member:** {member.mention}\n**From:** {before.channel.mention}\n**To:** {after.channel.mention}")
            embed.color = discord.Color.blue()
            await channel.send(embed=embed)


    @commands.hybrid_command(name="audit-config", description="[ADMIN] Configure the audit logging channels")
    @commands.has_permissions(administrator=True)
    async def audit_config(self, ctx: commands.Context):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT message_channel, member_channel, server_channel, voice_channel FROM audit_log_config WHERE guild_id = ?", (str(ctx.guild.id),))
        row = cursor.fetchone()

        if not row:
            cursor.execute("INSERT INTO audit_log_config (guild_id) VALUES (?)", (str(ctx.guild.id),))
            self.db_conn.commit()
            row = (None, None, None, None)

        view = ui_auditlog.AuditConfigView(self.db_conn, ctx.guild.id)
        embed = view.build_embed(row)
        await ctx.send(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AuditLog(bot))
