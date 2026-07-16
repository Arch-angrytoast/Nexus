import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import datetime
from . import ui_dossier
from . import ui_setup
from . import embed_factory

class ConfirmView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("You cannot confirm this.", ephemeral=True)
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("You cannot cancel this.", ephemeral=True)
        self.value = False
        await interaction.response.defer()
        self.stop()

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="ban", description="Ban a user from the server")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided."):
        if member == ctx.author:
            embed = embed_factory.create_clean_embed("❌ Error", "You cannot ban yourself.")
            await ctx.send(embed=embed)
            return

        if ctx.guild.me.top_role <= member.top_role:
            embed = embed_factory.create_clean_embed("❌ Error", "I cannot ban someone higher or equal to me in the role hierarchy.")
            await ctx.send(embed=embed)
            return

        view = ConfirmView(ctx)
        embed = embed_factory.create_clean_embed("⚠️ Confirm Ban", f"Are you sure you want to ban {member.mention}?\n**Reason:** {reason}")
        prompt_msg = await ctx.send(embed=embed, view=view, ephemeral=True)

        await view.wait()
        if view.value is None or view.value is False:
            embed = embed_factory.create_clean_embed("✅ Cancelled", "Ban cancelled.")
            await prompt_msg.edit(embed=embed, view=None)
            return

        try:
            await member.ban(reason=reason)
            embed = embed_factory.create_clean_embed("🔨 User Banned", f"Successfully banned **{member.name}**.\n**Reason:** {reason}", author=ctx.author)
            await prompt_msg.edit(embed=embed, view=None)
        except Exception as e:
            embed = embed_factory.create_clean_embed("❌ Error", f"Failed to ban user: {e}")
            await prompt_msg.edit(embed=embed, view=None)

    @commands.hybrid_command(name="kick", description="Kick a user from the server")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided."):
        if member == ctx.author:
            embed = embed_factory.create_clean_embed("❌ Error", "You cannot kick yourself.")
            await ctx.send(embed=embed)
            return

        try:
            await member.kick(reason=reason)
            embed = embed_factory.create_clean_embed("👢 User Kicked", f"Successfully kicked **{member.name}**.\n**Reason:** {reason}", author=ctx.author)
            await ctx.send(embed=embed)
        except Exception as e:
            embed = embed_factory.create_clean_embed("❌ Error", f"Failed to kick user: {e}")
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="purge", description="Purge messages in the current channel")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int):
        if amount <= 0 or amount > 100:
            embed = embed_factory.create_clean_embed("❌ Error", "Amount must be between 1 and 100.")
            await ctx.send(embed=embed)
            return

        view = ConfirmView(ctx)
        embed = embed_factory.create_clean_embed("⚠️ Confirm Purge", f"Are you sure you want to delete **{amount}** messages?")
        prompt_msg = await ctx.send(embed=embed, view=view, ephemeral=True)

        await view.wait()
        if view.value is None or view.value is False:
            embed = embed_factory.create_clean_embed("✅ Cancelled", "Purge cancelled.")
            await prompt_msg.edit(embed=embed, view=None)
            return

        try:
            deleted = await ctx.channel.purge(limit=amount + 1) # +1 to include the command msg
            embed = embed_factory.create_clean_embed("🧹 Messages Purged", f"Successfully deleted **{len(deleted) - 1}** messages.", author=ctx.author)
            await ctx.send(embed=embed, delete_after=5, ephemeral=True)
        except Exception as e:
            embed = embed_factory.create_clean_embed("❌ Error", f"Failed to purge messages: {e}")
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="warn", description="Warn a user")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, points: int, *, reason: str):
        if points <= 0 or points > 100:
            embed = embed_factory.create_clean_embed("❌ Error", "Points must be between 1 and 100.")
            await ctx.send(embed=embed)
            return

        cursor = self.bot.db_conn.cursor()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        cursor.execute('''
            INSERT INTO warnings (user_id, mod_id, reason, points, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (member.id, ctx.author.id, reason, points, now))
        self.bot.db_conn.commit()

        embed = embed_factory.create_clean_embed("⚠️ Warning Issued", f"**Target:** {member.mention}\n**Points:** +{points}\n**Reason:** {reason}", author=ctx.author)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clearwarnings", description="Clear all warnings for a user")
    @commands.has_permissions(administrator=True)
    async def clearwarnings(self, ctx: commands.Context, member: discord.Member):
        view = ConfirmView(ctx)
        embed = embed_factory.create_clean_embed("⚠️ Confirm Clear", f"Are you sure you want to clear **ALL** warnings for {member.mention}?")
        prompt_msg = await ctx.send(embed=embed, view=view, ephemeral=True)

        await view.wait()
        if view.value is None or view.value is False:
            embed = embed_factory.create_clean_embed("✅ Cancelled", "Action cancelled.")
            await prompt_msg.edit(embed=embed, view=None)
            return

        cursor = self.bot.db_conn.cursor()
        cursor.execute("DELETE FROM warnings WHERE user_id = ?", (member.id,))
        self.bot.db_conn.commit()

        embed = embed_factory.create_clean_embed("🧼 Warnings Cleared", f"All warnings for {member.mention} have been permanently deleted.", author=ctx.author)
        await prompt_msg.edit(embed=embed, view=None)

    @commands.hybrid_command(name="add-action", description="[ADMIN] Add a new roleplay action")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(action_name="Action name (e.g., punch, hug)", gifs="Comma-separated image URLs")
    async def add_action(self, ctx: commands.Context, action_name: str, *, gifs: str):
        import json
        name = action_name.lower().strip()
        gif_list = [g.strip() for g in gifs.split(',')]

        cursor = self.bot.db_conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO joke_actions (action_name, gifs) VALUES (?, ?)", (name, json.dumps(gif_list)))
        self.bot.db_conn.commit()

        embed = embed_factory.create_clean_embed("✅ Action Added", f"Action **{name}** added with {len(gif_list)} gifs.", author=ctx.author)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="remove-action", description="[ADMIN] Remove a roleplay action")
    @commands.has_permissions(administrator=True)
    async def remove_action(self, ctx: commands.Context, action_name: str):
        name = action_name.lower().strip()

        cursor = self.bot.db_conn.cursor()
        cursor.execute("DELETE FROM joke_actions WHERE action_name = ?", (name,))
        self.bot.db_conn.commit()

        embed = embed_factory.create_clean_embed("🗑️ Action Removed", f"Action **{name}** has been removed.", author=ctx.author)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="add-meter", description="[ADMIN] Add a new joke meter")
    @commands.has_permissions(administrator=True)
    async def add_meter(self, ctx: commands.Context, meter_name: str, emoji: str):
        name = meter_name.lower().strip()

        cursor = self.bot.db_conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO joke_meters (meter_name, emoji) VALUES (?, ?)", (name, emoji))
        self.bot.db_conn.commit()

        embed = embed_factory.create_clean_embed("✅ Meter Added", f"Meter **{name}** added with emoji {emoji}.", author=ctx.author)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="remove-meter", description="[ADMIN] Remove a joke meter")
    @commands.has_permissions(administrator=True)
    async def remove_meter(self, ctx: commands.Context, meter_name: str):
        name = meter_name.lower().strip()

        cursor = self.bot.db_conn.cursor()
        cursor.execute("DELETE FROM joke_meters WHERE meter_name = ?", (name,))
        self.bot.db_conn.commit()

        embed = embed_factory.create_clean_embed("🗑️ Meter Removed", f"Meter **{name}** has been removed.", author=ctx.author)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="dossier", description="[ADMIN] View detailed intelligence on a user")
    @commands.has_permissions(administrator=True)
    async def dossier(self, ctx: commands.Context, member: discord.Member):
        view = ui_dossier.DossierView(member, self.bot.db_conn)
        box = view.generate_identity_embed()

        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name="setup", description="[OWNER ONLY] Configure server channels and automod features")
    async def setup(self, ctx: commands.Context):
        import os
        owner_id = os.getenv("OWNER_ID")

        if str(ctx.author.id) != str(owner_id):
            embed = embed_factory.create_clean_embed("❌ Access Denied", "You do not have permission to use the setup menu. Only the explicitly defined Bot Owner can access this.")
            await ctx.send(embed=embed, ephemeral=True)
            return

        def generate_setup_embed():
            cursor = self.bot.db_conn.cursor()
            cursor.execute("SELECT key, value FROM server_config")
            config = dict(cursor.fetchall())

            def is_enabled(key):
                val = config.get(key, "1")
                return "🟢 Enabled" if val == "1" else "🔴 Disabled"

            gen_chan = self.bot.get_channel(int(config.get("general_channel", 0)))
            spam_chan = self.bot.get_channel(int(config.get("spam_channel", 0)))

            gen_str = gen_chan.mention if gen_chan else "Not Set"
            spam_str = spam_chan.mention if spam_chan else "Not Set"

            toggles = [
                f"**Anti-Spam/Velocity:** {is_enabled('anti_spam')}",
                f"**Anti-Links:** {is_enabled('anti_links')}",
                f"**English Only (GenChat):** {is_enabled('english_only')}",
                f"**No Bot Commands (GenChat):** {is_enabled('no_bot_commands')}"
            ]
            toggles_str = "\n".join(toggles)

            banned_words = [v for k, v in config.items() if k.startswith("banned_word_")]
            word_count = len(banned_words)

            content = "Use the dropdowns below to configure server channels and toggle automod features.\n\n"
            content += f"**🎛️ Filter Status**\n{toggles_str}\n\n"
            content += f"**🛡️ Anti-Nuke Status:** {is_enabled('antinuke')}\n\n"
            content += f"**💬 General Channel:** {gen_str}\n*(Enforces English-only and blocks bot commands)*\n\n"
            content += f"**🗑️ Spam Channel:** {spam_str}\n*(Exempt from spam/velocity rules)*\n\n"
            content += f"**🛑 Banned Words:** **{word_count}** words blacklisted."

            return embed_factory.create_clean_embed("⚙️ Nexus Server Setup", content)

        embed = generate_setup_embed()
        view = ui_setup.SetupView(self.bot.db_conn, generate_setup_embed)

        await ctx.send(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
