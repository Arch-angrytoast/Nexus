import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import datetime
from . import embed_factory

class CloseTicketView(discord.ui.View):
    def __init__(self, db_conn: sqlite3.Connection):
        super().__init__(timeout=None)
        self.db_conn = db_conn

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.type == discord.ChannelType.private_thread and not interaction.channel.type == discord.ChannelType.text:
            return

        # Double check it is a ticket channel
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT ticket_id, user_id FROM tickets WHERE channel_id = ? AND status = 'open'", (interaction.channel.id,))
        row = cursor.fetchone()

        if not row:
            await interaction.response.send_message("This does not appear to be an open ticket channel.", ephemeral=True)
            return

        ticket_id, user_id = row

        # Mark closed in DB
        cursor.execute("UPDATE tickets SET status = 'closed' WHERE ticket_id = ?", (ticket_id,))
        self.db_conn.commit()

        embed = embed_factory.create_clean_embed("🔒 Ticket Closed", f"Ticket #{ticket_id} has been closed by {interaction.user.mention}. This channel will be deleted in 5 seconds.")
        await interaction.response.send_message(embed=embed)

        import asyncio
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket #{ticket_id} closed by {interaction.user.name}")
        except Exception as e:
            print(f"Failed to delete ticket channel: {e}")

class TicketModal(discord.ui.Modal, title='Open a Support Ticket'):
    subject = discord.ui.TextInput(
        label='Subject',
        placeholder='Short description of your issue...',
        min_length=3,
        max_length=50,
        required=True
    )

    description = discord.ui.TextInput(
        label='Description',
        style=discord.TextStyle.long,
        placeholder='Please describe your issue in detail...',
        min_length=10,
        max_length=1000,
        required=True
    )

    def __init__(self, db_conn: sqlite3.Connection):
        super().__init__()
        self.db_conn = db_conn


    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        cursor = self.db_conn.cursor()
        cursor.execute("SELECT ticket_id, channel_id FROM tickets WHERE user_id = ? AND status = 'open'", (interaction.user.id,))
        existing = cursor.fetchone()
        if existing:
            await interaction.followup.send(f"You already have an open ticket in <#{existing[1]}>.", ephemeral=True)
            return

        cursor.execute("SELECT key, value FROM ticket_config")
        config = dict(cursor.fetchall())

        guild = interaction.guild
        category_id = config.get("ticket_category")
        support_role_id = config.get("support_role")

        category = discord.utils.get(guild.categories, id=int(category_id)) if category_id else None
        if not category:
            try:
                category = await guild.create_category("Tickets")
            except discord.Forbidden:
                await interaction.followup.send("Failed to create ticket: I lack 'Manage Channels' permission and no category is set.", ephemeral=True)
                return

        support_role = guild.get_role(int(support_role_id)) if support_role_id else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor.execute("INSERT INTO tickets (user_id, channel_id, status, created_at) VALUES (?, 0, 'open', ?)", (interaction.user.id, now))
        self.db_conn.commit()
        ticket_id = cursor.lastrowid

        channel_name = f"ticket-{ticket_id}-{interaction.user.name.lower()}"

        try:
            ticket_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)

            cursor.execute("UPDATE tickets SET channel_id = ? WHERE ticket_id = ?", (ticket_channel.id, ticket_id))
            self.db_conn.commit()

            embed = embed_factory.create_clean_embed(
                f"🎫 Ticket #{ticket_id}",
                f"**Created By:** {interaction.user.mention}\n**Subject:** {self.subject.value}\n\n**Description:**\n{self.description.value}\n\n*Support will be with you shortly.*",

                color=discord.Color.blue()
            )

            view = CloseTicketView(self.db_conn)
            ping_str = f"{interaction.user.mention}"
            if support_role:
                ping_str += f" {support_role.mention}"
            await ticket_channel.send(content=ping_str, embed=embed, view=view)

            await interaction.followup.send(f"Your ticket has been created: {ticket_channel.mention}", ephemeral=True)
        except Exception as e:
            cursor.execute("DELETE FROM tickets WHERE ticket_id = ?", (ticket_id,))
            self.db_conn.commit()
            await interaction.followup.send(f"Failed to create ticket channel: {e}", ephemeral=True)

class OpenTicketView(discord.ui.View):
    def __init__(self, db_conn: sqlite3.Connection):
        super().__init__(timeout=None)
        self.db_conn = db_conn

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket_btn", emoji="📩")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal(self.db_conn))

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_conn = bot.db_conn

    @commands.Cog.listener()
    async def on_ready(self):
        # Register persistent views
        self.bot.add_view(OpenTicketView(self.db_conn))
        self.bot.add_view(CloseTicketView(self.db_conn))


    @commands.hybrid_command(name="setup-tickets-config", description="[ADMIN] Configure the ticket system settings")
    @commands.has_permissions(administrator=True)
    async def setup_tickets_config(self, ctx: commands.Context):
        from . import ui_tickets
        def generate_setup_embed():
            cursor = self.bot.db_conn.cursor()
            cursor.execute("SELECT key, value FROM ticket_config")
            config = dict(cursor.fetchall())

            title = config.get("panel_title", "🎫 Support Tickets")
            desc = config.get("panel_desc", "Click the button below to open a private support ticket.\n\nPlease be prepared to provide a detailed description of your issue so our staff can assist you promptly.")

            role_id = config.get("support_role")
            cat_id = config.get("ticket_category")

            role_str = f"<@&{role_id}>" if role_id else "Not Set"
            cat_str = f"<#{cat_id}>" if cat_id else "Not Set (Auto-creates 'Tickets')"

            content = "Use the dropdown below to configure the ticket system.\n\n"
            content += f"**Panel Title:** {title}\n"
            content += f"**Panel Description:** {desc}\n"
            content += f"**Support Role:** {role_str}\n"
            content += f"**Ticket Category:** {cat_str}"

            return embed_factory.create_clean_embed("⚙️ Ticket System Config", content)

        embed = generate_setup_embed()
        view = ui_tickets.TicketSetupView(self.bot.db_conn, generate_setup_embed)
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name="spawn-ticket-panel", description="[ADMIN] Spawn the interactive ticket panel")
    @commands.has_permissions(administrator=True)
    async def spawn_ticket_panel(self, ctx: commands.Context):
        cursor = self.bot.db_conn.cursor()
        cursor.execute("SELECT key, value FROM ticket_config")
        config = dict(cursor.fetchall())

        title = config.get("panel_title", "🎫 Support Tickets")
        desc = config.get("panel_desc", "Click the button below to open a private support ticket.\n\nPlease be prepared to provide a detailed description of your issue so our staff can assist you promptly.")

        embed = embed_factory.create_clean_embed(title, desc)
        view = OpenTicketView(self.db_conn)
        await ctx.send(embed=embed, view=view)
        if ctx.message:
            try:
                await ctx.message.delete()
            except:
                pass
