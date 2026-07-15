import discord
from discord.ext import commands
from discord import app_commands
import datetime
from . import ui_setup
from . import ui_confirm
from . import ui_dossier
import os

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="kick", description="Kick a user from the server")
    @app_commands.describe(member="The member to kick", reason="The reason for the kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("You cannot kick someone with an equal or higher role than you.", ephemeral=True)
            return

        try:
            await member.kick(reason=reason)
            embed = discord.Embed(
                title="User Kicked",
                description=f"**{member.display_name}** has been kicked.\n**Reason:** {reason}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I do not have permission to kick this user. Make sure my role is higher than theirs.", ephemeral=True)

    @commands.hybrid_command(name="ban", description="Ban a user from the server")
    @app_commands.describe(member="The member to ban", reason="The reason for the ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("You cannot ban someone with an equal or higher role than you.", ephemeral=True)
            return

        view = ui_confirm.ConfirmView(ctx.author.id)
        embed = discord.Embed(
            title="⚠️ Confirm Ban",
            description=f"Are you sure you want to permanently ban **{member.mention}**?\n**Reason:** {reason}",
            color=discord.Color.red()
        )
        prompt_msg = await ctx.send(embed=embed, view=view, ephemeral=True)
        await view.wait()

        if not view.value:
            embed.description = "Ban cancelled."
            embed.color = discord.Color.green()
            await prompt_msg.edit(embed=embed, view=None)
            return

        try:
            await member.ban(reason=reason)
            embed = discord.Embed(
                title="🔨 User Banned",
                description=f"**{member.display_name}** has been banned.\n**Reason:** {reason}",
                color=discord.Color.dark_red()
            )
            await prompt_msg.edit(embed=embed, view=None)
        except discord.Forbidden:
            await ctx.send("I do not have permission to ban this user. Make sure my role is higher than theirs.", ephemeral=True)

    @commands.hybrid_command(name="unban", description="Unban a user by their user ID")
    @app_commands.describe(user_id="The ID of the user to unban")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: str):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user)
            embed = discord.Embed(
                title="User Unbanned",
                description=f"**{user.display_name}** has been unbanned.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except ValueError:
            await ctx.send("Please provide a valid numeric User ID.", ephemeral=True)
        except discord.NotFound:
            await ctx.send("User is not banned or could not be found.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("I do not have permission to unban users.", ephemeral=True)

    @commands.hybrid_command(name="purge", aliases=["clear"], description="Delete messages in the channel")
    @app_commands.describe(amount="Number of messages to scan/delete (max 100)", target="Optional: Only delete messages from this user")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int, target: discord.Member = None):
        if amount < 1 or amount > 100:
            await ctx.send("Please provide a number between 1 and 100.", ephemeral=True)
            return

        # UI Confirmation for large purges to prevent accidents
        if amount >= 20:
            view = ui_confirm.ConfirmView(ctx.author.id)
            target_str = f" from {target.mention}" if target else ""
            embed = discord.Embed(
                title="⚠️ Confirm Purge",
                description=f"Are you sure you want to scan and delete **{amount}** messages{target_str} in this channel?",
                color=discord.Color.brand_red()
            )
            prompt_msg = await ctx.send(embed=embed, view=view, ephemeral=True)
            await view.wait()

            if not view.value:
                embed.description = "Purge cancelled."
                embed.color = discord.Color.green()
                await prompt_msg.edit(embed=embed, view=None)
                return
            else:
                await prompt_msg.delete()

        await ctx.defer(ephemeral=True)

        def check(m):
            if target:
                return m.author.id == target.id
            return True

        try:
            # Delete the invocation message first if it was a prefix command
            if ctx.interaction is None:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass

            deleted = await ctx.channel.purge(limit=amount, check=check)

            embed = discord.Embed(
                title="🗑️ Purge Complete",
                description=f"Successfully deleted **{len(deleted)}** messages.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed, delete_after=5, ephemeral=True)

        except discord.Forbidden:
            await ctx.send("I do not have permission to manage messages.", ephemeral=True)
        except discord.HTTPException:
            await ctx.send("Failed to delete messages. Messages older than 14 days cannot be bulk deleted.", ephemeral=True)

    @commands.hybrid_command(name="timeout", description="Timeout a user for a specified duration")
    @app_commands.describe(member="The member to timeout", minutes="Duration in minutes", reason="The reason for the timeout")
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, member: discord.Member, minutes: int, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("You cannot timeout someone with an equal or higher role than you.", ephemeral=True)
            return

        if minutes < 1 or minutes > 40320: # Discord max is 28 days
            await ctx.send("Timeout duration must be between 1 and 40,320 minutes (28 days).", ephemeral=True)
            return

        duration = datetime.timedelta(minutes=minutes)
        try:
            await member.timeout(duration, reason=reason)
            embed = discord.Embed(
                title="User Timed Out",
                description=f"**{member.display_name}** has been timed out for {minutes} minutes.\n**Reason:** {reason}",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I do not have permission to timeout this user.", ephemeral=True)


    @commands.hybrid_command(name="warn", description="Manually issue a warning to a user")
    @app_commands.describe(member="The member to warn", points="The number of points to assign", reason="The reason for the warning")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, points: int, *, reason: str):
        if points < 1 or points > 100:
            await ctx.send("Points must be between 1 and 100.", ephemeral=True)
            return

        utc_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor = self.bot.db_conn.cursor()
        cursor.execute(
            "INSERT INTO warnings (user_id, mod_id, reason, points, timestamp) VALUES (?, ?, ?, ?, ?)",
            (member.id, ctx.author.id, reason, points, utc_now)
        )
        self.bot.db_conn.commit()

        thirty_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat()
        cursor.execute(
            "SELECT SUM(points) FROM warnings WHERE user_id = ? AND timestamp > ?",
            (member.id, thirty_days_ago)
        )
        total_points = cursor.fetchone()[0] or 0

        embed = discord.Embed(
            title="User Warned",
            description=f"**{member.display_name}** has been warned by **{ctx.author.display_name}**.\n**Reason:** {reason}\n**Points Assigned:** {points}\n**Total Points (30d):** {total_points}",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

        # Note: Manual warnings do not trigger the automod escalations automatically. Mods should handle escalation manually if applying points manually.

    @commands.hybrid_command(name="warnings", description="View a user's warning history")
    @app_commands.describe(member="The member to view")
    @commands.has_permissions(manage_messages=True)
    async def warnings(self, ctx: commands.Context, member: discord.Member):
        cursor = self.bot.db_conn.cursor()
        cursor.execute(
            "SELECT mod_id, reason, points, timestamp FROM warnings WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10",
            (member.id,)
        )
        rows = cursor.fetchall()

        thirty_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat()
        cursor.execute(
            "SELECT SUM(points) FROM warnings WHERE user_id = ? AND timestamp > ?",
            (member.id, thirty_days_ago)
        )
        total_points = cursor.fetchone()[0] or 0

        if not rows:
            await ctx.send(f"**{member.display_name}** has no warnings on record.", ephemeral=True)
            return

        description_lines = []
        for mod_id, reason, points, timestamp in rows:
            dt = datetime.datetime.fromisoformat(timestamp)
            formatted_date = dt.strftime("%Y-%m-%d")
            description_lines.append(f"• **{formatted_date}**: {points} pts - {reason} (by <@{mod_id}>)")

        embed = discord.Embed(
            title=f"Warning History for {member.display_name}",
            description="\n".join(description_lines) + f"\n\n**Total Points (last 30 days):** {total_points}",
            color=discord.Color.dark_theme()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clearwarnings", description="Clear all warnings for a user")
    @app_commands.describe(member="The member to clear warnings for")
    @commands.has_permissions(administrator=True)
    async def clearwarnings(self, ctx: commands.Context, member: discord.Member):
        cursor = self.bot.db_conn.cursor()
        cursor.execute("DELETE FROM warnings WHERE user_id = ?", (member.id,))
        deleted = cursor.rowcount
        self.bot.db_conn.commit()

        await ctx.send(f"Cleared {deleted} warnings for **{member.display_name}**.")

    @commands.hybrid_command(name="lockdown", description="Lockdown the current channel, preventing members from sending messages")
    @commands.has_permissions(manage_channels=True)
    async def lockdown(self, ctx: commands.Context):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False, reason=f"Lockdown initiated by {ctx.author.display_name}")
        embed = discord.Embed(
            title="🔒 Channel Locked",
            description="This channel has been locked by a moderator. You can no longer send messages here until it is unlocked.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="unlock", description="Unlock the current channel, allowing members to send messages again")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None, reason=f"Unlock initiated by {ctx.author.display_name}")
        embed = discord.Embed(
            title="🔓 Channel Unlocked",
            description="This channel has been unlocked. Normal chat permissions have been restored.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)



    @commands.hybrid_command(name="dossier", description="[OWNER ONLY] Pull a classified dossier on a user")
    @app_commands.describe(member="The member to investigate")
    async def dossier(self, ctx: commands.Context, member: discord.Member):
        owner_id = os.getenv("OWNER_ID")
        if str(ctx.author.id) != str(owner_id):
            await ctx.send("CLASSIFIED: You do not have the required clearance to use this command.", ephemeral=True)
            return

        view = ui_dossier.DossierView(member, self.bot.db_conn)
        embed = view.generate_identity_embed()

        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name="setup", description="[OWNER ONLY] Open the interactive Automod & Anti-Nuke dashboard")
    async def setup_dashboard(self, ctx: commands.Context):
        # Strict Security: Only the Server Owner or Bot Owner can manage the core defense systems.
        owner_id = str(os.getenv("OWNER_ID"))
        if str(ctx.author.id) != owner_id and ctx.author.id != ctx.guild.owner_id:
            embed = discord.Embed(
                title="⛔ Access Denied",
                description="For security reasons, only the Server Owner can access the configuration dashboard.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        def generate_setup_embed():
            cursor = self.bot.db_conn.cursor()
            cursor.execute("SELECT key, value FROM server_config")
            rows = cursor.fetchall()
            config_dict = {k: v for k, v in rows}

            gen_ch = config_dict.get("general_channel")
            gen_str = f"<#{gen_ch}>" if gen_ch else "*Not Set*"

            spam_ch = config_dict.get("spam_channel")
            spam_str = f"<#{spam_ch}>" if spam_ch else "*Not Set*"

            words = config_dict.get("banned_words", "")
            word_count = len([w for w in words.split(',') if w.strip()]) if words else 0

            def is_enabled(key: str) -> str:
                val = config_dict.get(key)
                return "🟢 ON" if val is None or val == "1" else "🔴 OFF"

            embed = discord.Embed(
                title="⚙️ Automod Setup Dashboard",
                description="Use the dropdown menu below to configure the Automod settings.",
                color=discord.Color.blurple()
            )

            # Status overview
            toggles_str = f"**Links:** {is_enabled('filter_links')} | **Words:** {is_enabled('filter_words')} | **English:** {is_enabled('filter_english')} | **Commands:** {is_enabled('filter_commands')} | **Spam:** {is_enabled('filter_spam')}"
            embed.add_field(name="🎛️ Filter Status", value=toggles_str, inline=False)
            embed.add_field(name="🛡️ Anti-Nuke Status", value=is_enabled('antinuke'), inline=False)

            embed.add_field(name="💬 General Channel", value=f"{gen_str}\n*(Enforces English-only and blocks bot commands)*", inline=False)
            embed.add_field(name="🗑️ Spam Channel", value=f"{spam_str}\n*(Exempt from spam/velocity rules)*", inline=False)
            embed.add_field(name="🛑 Banned Words", value=f"**{word_count}** words blacklisted.", inline=False)
            return embed

        embed = generate_setup_embed()
        view = ui_setup.SetupView(self.bot.db_conn, generate_setup_embed)

        await ctx.send(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
