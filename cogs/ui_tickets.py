import discord
from discord.ext import commands
import sqlite3
from . import embed_factory

class TicketConfigModal(discord.ui.Modal):
    def __init__(self, db_conn: sqlite3.Connection, key: str, current_val: str, title: str, view_to_refresh):
        super().__init__(title=title)
        self.db_conn = db_conn
        self.key = key
        self.view_to_refresh = view_to_refresh

        self.value_input = discord.ui.TextInput(
            label="New Value",
            style=discord.TextStyle.long if "desc" in key else discord.TextStyle.short,
            default=current_val,
            required=True
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        cursor = self.db_conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO ticket_config (key, value) VALUES (?, ?)", (self.key, self.value_input.value))
        self.db_conn.commit()
        await self.view_to_refresh.refresh_embed(interaction)

class TicketConfigDropdown(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label="Edit Panel Title", value="panel_title", emoji="📝", description="The title of the spawnable ticket panel"),
            discord.SelectOption(label="Edit Panel Description", value="panel_desc", emoji="📖", description="The text inside the spawnable ticket panel"),
            discord.SelectOption(label="Set Support Role", value="support_role", emoji="🛡️", description="The role pinged and added to tickets"),
            discord.SelectOption(label="Set Category", value="ticket_category", emoji="📂", description="The category where tickets spawn")
        ]
        super().__init__(placeholder="Select a setting to configure...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        cursor = self.parent_view.db_conn.cursor()
        key = self.values[0]

        if key in ["support_role", "ticket_category"]:
            # Handle role/channel selection via a specialized view instead of text modal
            self.parent_view.clear_items()
            if key == "support_role":
                self.parent_view.add_item(TicketRoleSelect(self.parent_view))
            else:
                self.parent_view.add_item(TicketCategorySelect(self.parent_view))

            embed = self.parent_view.generate_embed_func()
            await interaction.response.edit_message(embed=embed, view=self.parent_view)
        else:
            cursor.execute("SELECT value FROM ticket_config WHERE key = ?", (key,))
            row = cursor.fetchone()
            current_val = row[0] if row else ""

            title = "Edit Panel Title" if key == "panel_title" else "Edit Panel Description"
            modal = TicketConfigModal(self.parent_view.db_conn, key, current_val, title, self.parent_view)
            await interaction.response.send_modal(modal)

class TicketRoleSelect(discord.ui.RoleSelect):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        super().__init__(placeholder="Select the Support Role...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO ticket_config (key, value) VALUES (?, ?)", ("support_role", str(role.id)))
        self.parent_view.db_conn.commit()
        await self.parent_view.refresh_embed(interaction)

class TicketCategorySelect(discord.ui.ChannelSelect):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        super().__init__(placeholder="Select the Ticket Category...", min_values=1, max_values=1, channel_types=[discord.ChannelType.category])

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO ticket_config (key, value) VALUES (?, ?)", ("ticket_category", str(cat.id)))
        self.parent_view.db_conn.commit()
        await self.parent_view.refresh_embed(interaction)

class TicketSetupView(discord.ui.View):
    def __init__(self, db_conn: sqlite3.Connection, generate_embed_func):
        super().__init__(timeout=600)
        self.db_conn = db_conn
        self.generate_embed_func = generate_embed_func
        self.add_item(TicketConfigDropdown(self))

    async def refresh_embed(self, interaction: discord.Interaction):
        embed = self.generate_embed_func()
        self.clear_items()
        self.add_item(TicketConfigDropdown(self))
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            pass
