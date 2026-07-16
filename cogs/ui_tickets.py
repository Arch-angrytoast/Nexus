import discord
from discord.ext import commands
import sqlite3
import datetime
from . import embed_factory

# --- TICKET CREATION LOGIC (Used by the final published panel) ---

class CloseTicketView(discord.ui.View):
    def __init__(self, db_conn: sqlite3.Connection):
        super().__init__(timeout=None)
        self.db_conn = db_conn

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT ticket_id FROM tickets WHERE channel_id = ? AND status = 'open'", (interaction.channel.id,))
        row = cursor.fetchone()

        if not row:
            await interaction.response.send_message("This does not appear to be an open ticket channel.", ephemeral=True)
            return

        ticket_id = row[0]
        cursor.execute("UPDATE tickets SET status = 'closed' WHERE ticket_id = ?", (ticket_id,))
        self.db_conn.commit()

        embed = embed_factory.create_clean_embed("🔒 Ticket Closed", f"Ticket #{ticket_id} closed by {interaction.user.mention}. Deleting in 5 seconds.")
        await interaction.response.send_message(embed=embed)

        import asyncio
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass

class UserTicketModal(discord.ui.Modal, title='Open Ticket'):
    subject = discord.ui.TextInput(label='Subject', placeholder='Short description...', min_length=3, max_length=50)
    description = discord.ui.TextInput(label='Description', style=discord.TextStyle.long, min_length=10, max_length=1000)

    def __init__(self, db_conn: sqlite3.Connection, button_id: int):
        super().__init__()
        self.db_conn = db_conn
        self.button_id = button_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cursor = self.db_conn.cursor()

        # Prevent spam
        cursor.execute("SELECT channel_id FROM tickets WHERE user_id = ? AND status = 'open'", (interaction.user.id,))
        if cursor.fetchone():
            await interaction.followup.send("You already have an open ticket.", ephemeral=True)
            return

        # Get button config
        cursor.execute("SELECT label, ping_role_id, category_id FROM ticket_buttons WHERE button_id = ?", (self.button_id,))
        btn_data = cursor.fetchone()
        if not btn_data:
            await interaction.followup.send("This ticket button is invalid.", ephemeral=True)
            return

        label, role_id, cat_id = btn_data
        guild = interaction.guild

        # Fallbacks
        cursor.execute("SELECT key, value FROM ticket_config")
        config = dict(cursor.fetchall())

        category_id = cat_id or config.get("default_category")
        ping_role_id = role_id or config.get("default_support_role")
        initial_msg = config.get("default_initial_message", "Support will be with you shortly.")

        category = guild.get_channel(int(category_id)) if category_id else None
        support_role = guild.get_role(int(ping_role_id)) if ping_role_id else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor.execute("INSERT INTO tickets (user_id, channel_id, status, created_at) VALUES (?, 0, 'open', ?)", (interaction.user.id, now))
        self.db_conn.commit()
        ticket_id = cursor.lastrowid

        channel_name = f"{label.lower()}-{ticket_id}"

        try:
            ticket_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
            cursor.execute("UPDATE tickets SET channel_id = ? WHERE ticket_id = ?", (ticket_channel.id, ticket_id))
            self.db_conn.commit()

            embed = embed_factory.create_clean_embed(
                f"🎫 {label} Ticket #{ticket_id}",
                f"**Creator:** {interaction.user.mention}\n**Subject:** {self.subject.value}\n\n**Description:**\n{self.description.value}\n\n*{initial_msg}*"
            )

            ping_str = f"{interaction.user.mention}"
            if support_role:
                ping_str += f" {support_role.mention}"

            await ticket_channel.send(content=ping_str, embed=embed, view=CloseTicketView(self.db_conn))
            await interaction.followup.send(f"Ticket created: {ticket_channel.mention}", ephemeral=True)
        except Exception as e:
            cursor.execute("DELETE FROM tickets WHERE ticket_id = ?", (ticket_id,))
            self.db_conn.commit()
            await interaction.followup.send(f"Failed to create ticket: {e}", ephemeral=True)

class PublishedTicketButton(discord.ui.Button):
    def __init__(self, db_conn, btn_id, label, emoji):
        super().__init__(style=discord.ButtonStyle.secondary, label=label, emoji=emoji, custom_id=f"pub_ticket_{btn_id}")
        self.db_conn = db_conn
        self.btn_id = btn_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(UserTicketModal(self.db_conn, self.btn_id))

class PublishedPanelView(discord.ui.View):
    def __init__(self, db_conn: sqlite3.Connection):
        super().__init__(timeout=None)
        self.db_conn = db_conn

        cursor = db_conn.cursor()
        cursor.execute("SELECT button_id, label, emoji FROM ticket_buttons WHERE panel_id = 'default'")
        for btn_id, label, emoji in cursor.fetchall():
            self.add_item(PublishedTicketButton(db_conn, btn_id, label, emoji))


# --- TICKET BUILDER (setup-tickets) ---

class AddButtonModal(discord.ui.Modal, title="Add Ticket Type"):
    btn_label = discord.ui.TextInput(label="Button Label (e.g. Support)", max_length=30)
    btn_emoji = discord.ui.TextInput(label="Emoji (Optional)", required=False, max_length=10)
    btn_role = discord.ui.TextInput(label="Specific Ping Role ID (Optional)", required=False)
    btn_cat = discord.ui.TextInput(label="Specific Category ID (Optional)", required=False)

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute(
            "INSERT INTO ticket_buttons (panel_id, label, emoji, ping_role_id, category_id) VALUES (?, ?, ?, ?, ?)",
            ("default", self.btn_label.value, self.btn_emoji.value or None, self.btn_role.value or None, self.btn_cat.value or None)
        )
        self.parent_view.db_conn.commit()
        await self.parent_view.refresh(interaction)

class EditPanelTextModal(discord.ui.Modal, title="Edit Panel Text"):
    p_title = discord.ui.TextInput(label="Title", default="Support Tickets")
    p_desc = discord.ui.TextInput(label="Description", style=discord.TextStyle.long, default="Select a category below.")

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO ticket_config (key, value) VALUES ('panel_title', ?)", (self.p_title.value,))
        cursor.execute("INSERT OR REPLACE INTO ticket_config (key, value) VALUES ('panel_desc', ?)", (self.p_desc.value,))
        self.parent_view.db_conn.commit()
        await self.parent_view.refresh(interaction)

class BuilderButtonDeleteSelect(discord.ui.Select):
    def __init__(self, parent_view, options):
        self.parent_view = parent_view
        super().__init__(placeholder="Select a button to delete...", options=options)

    async def callback(self, interaction: discord.Interaction):
        btn_id = self.values[0]
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute("DELETE FROM ticket_buttons WHERE button_id = ?", (btn_id,))
        self.parent_view.db_conn.commit()
        await self.parent_view.refresh(interaction)

class TicketBuilderView(discord.ui.View):
    def __init__(self, db_conn: sqlite3.Connection):
        super().__init__(timeout=600)
        self.db_conn = db_conn

    def build_preview_embed(self):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT key, value FROM ticket_config")
        config = dict(cursor.fetchall())
        title = config.get("panel_title", "Support Tickets")
        desc = config.get("panel_desc", "Select a category below.")

        embed = embed_factory.create_clean_embed(f"[PREVIEW] {title}", desc)

        cursor.execute("SELECT button_id, label, emoji, ping_role_id, category_id FROM ticket_buttons WHERE panel_id = 'default'")
        btns = cursor.fetchall()
        if btns:
            info = ""
            for b_id, lbl, emj, r_id, c_id in btns:
                info += f"• {emj or ''} **{lbl}** (Role: {r_id or 'Default'}, Cat: {c_id or 'Default'})\n"
            embed.add_field(name="Configured Buttons", value=info, inline=False)
        else:
            embed.add_field(name="Configured Buttons", value="None yet. Click 'Add Button'.", inline=False)

        return embed

    async def refresh(self, interaction: discord.Interaction):
        self.clear_items()

        # Add core builder buttons
        self.add_item(discord.ui.Button(label="Edit Text", style=discord.ButtonStyle.primary, custom_id="tb_edit_text"))
        self.add_item(discord.ui.Button(label="Add Button", style=discord.ButtonStyle.success, custom_id="tb_add_btn"))
        self.add_item(discord.ui.Button(label="Publish Panel", style=discord.ButtonStyle.danger, custom_id="tb_publish"))

        # Add delete dropdown if there are buttons
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT button_id, label FROM ticket_buttons WHERE panel_id = 'default'")
        btns = cursor.fetchall()
        if btns:
            opts = [discord.SelectOption(label=f"Delete: {lbl}", value=str(b_id)) for b_id, lbl in btns[:25]]
            self.add_item(BuilderButtonDeleteSelect(self, opts))

        embed = self.build_preview_embed()

        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data.get("custom_id") == "tb_edit_text":
            await interaction.response.send_modal(EditPanelTextModal(self))
            return False
        elif interaction.data.get("custom_id") == "tb_add_btn":
            await interaction.response.send_modal(AddButtonModal(self))
            return False
        elif interaction.data.get("custom_id") == "tb_publish":
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT key, value FROM ticket_config")
            config = dict(cursor.fetchall())
            embed = embed_factory.create_clean_embed(config.get("panel_title", "Support Tickets"), config.get("panel_desc", "Select a category below."))
            view = PublishedPanelView(self.db_conn)
            await interaction.channel.send(embed=embed, view=view)
            await interaction.response.send_message("Panel published!", ephemeral=True)
            return False
        return True


# --- TICKET CONFIG (ticket-config) ---

class GlobalConfigModal(discord.ui.Modal, title="Edit Ticket Config"):
    def __init__(self, db_conn, key, current_val):
        super().__init__()
        self.db_conn = db_conn
        self.key = key
        self.val_input = discord.ui.TextInput(label="New Value (ID or Text)", default=current_val, style=discord.TextStyle.long if "message" in key else discord.TextStyle.short)
        self.add_item(self.val_input)

    async def on_submit(self, interaction: discord.Interaction):
        cursor = self.db_conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO ticket_config (key, value) VALUES (?, ?)", (self.key, self.val_input.value))
        self.db_conn.commit()
        await interaction.response.send_message("Saved! Run `/ticket-config` again to see changes.", ephemeral=True)

class GlobalConfigDropdown(discord.ui.Select):
    def __init__(self, db_conn):
        self.db_conn = db_conn
        opts = [
            discord.SelectOption(label="Default Initial Message", value="default_initial_message", description="Message sent when a ticket opens"),
            discord.SelectOption(label="Default Support Role ID", value="default_support_role", description="Role ID pinged automatically"),
            discord.SelectOption(label="Default Category ID", value="default_category", description="Category ID where tickets spawn")
        ]
        super().__init__(placeholder="Select a global setting...", options=opts)

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT value FROM ticket_config WHERE key = ?", (key,))
        row = cursor.fetchone()
        current_val = row[0] if row else ""
        await interaction.response.send_modal(GlobalConfigModal(self.db_conn, key, current_val))

class GlobalConfigView(discord.ui.View):
    def __init__(self, db_conn):
        super().__init__(timeout=600)
        self.add_item(GlobalConfigDropdown(db_conn))
