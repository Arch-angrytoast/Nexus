import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from . import embed_factory
from . import ui_tickets

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_conn = bot.db_conn

    @commands.Cog.listener()
    async def on_ready(self):
        # Register persistent published views
        cursor = self.db_conn.cursor()

        # Check if table exists to avoid errors on first start before init
        try:
            cursor.execute("SELECT panel_id FROM ticket_panels")
            panels = cursor.fetchall()
            for (p_id,) in panels:
                self.bot.add_view(ui_tickets.PublishedPanelView(self.db_conn, panel_id=p_id))
        except Exception:
            self.bot.add_view(ui_tickets.PublishedPanelView(self.db_conn))

        self.bot.add_view(ui_tickets.TicketManageView(self.db_conn))

    @commands.hybrid_command(name="ticket-setup", description="[ADMIN] Open the Ticket Panel Builder")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx: commands.Context, panel_id: str = "default"):
        panel_id = panel_id.lower()
        cursor = self.db_conn.cursor()

        # Ensure panel exists in DB
        cursor.execute("SELECT panel_id FROM ticket_panels WHERE panel_id = ?", (panel_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO ticket_panels (panel_id, title, description, initial_message, claimed_message)
                VALUES (?, ?, ?, ?, ?)
            ''', (panel_id, f"{panel_id.title()} Support", "Select a category below to open a ticket.", "Support will be with you shortly.", "Your ticket has been claimed."))
            self.db_conn.commit()

        view = ui_tickets.TicketBuilderView(self.db_conn, panel_id)
        embed = view.build_preview_embed()

        # Add buttons manually just for the first send
        view.add_item(discord.ui.Button(label="Edit Text", style=discord.ButtonStyle.primary, custom_id=f"tb_edit_text_{panel_id}"))
        view.add_item(discord.ui.Button(label="Add Button", style=discord.ButtonStyle.success, custom_id=f"tb_add_btn_{panel_id}"))
        view.add_item(discord.ui.Button(label="Publish Panel", style=discord.ButtonStyle.danger, custom_id=f"tb_publish_{panel_id}"))

        cursor.execute("SELECT button_id, label FROM ticket_buttons WHERE panel_id = ?", (panel_id,))
        btns = cursor.fetchall()
        if btns:
            opts_del = [discord.SelectOption(label=f"Delete: {lbl}", value=str(b_id)) for b_id, lbl in btns[:25]]
            opts_edit = [discord.SelectOption(label=f"Edit: {lbl}", value=str(b_id)) for b_id, lbl in btns[:25]]
            view.add_item(ui_tickets.BuilderButtonActionSelect(view, opts_edit, "edit"))
            view.add_item(ui_tickets.BuilderButtonActionSelect(view, opts_del, "delete"))

        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name="ticket-config", description="[ADMIN] Configure settings for a specific ticket panel")
    @commands.has_permissions(administrator=True)
    async def ticket_config(self, ctx: commands.Context, panel_id: str = "default"):
        panel_id = panel_id.lower()
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT * FROM ticket_panels WHERE panel_id = ?", (panel_id,))
        row = cursor.fetchone()

        if not row:
            await ctx.send(f"Panel `{panel_id}` does not exist. Create it first using `/ticket-setup {panel_id}`.", ephemeral=True)
            return

        # Unpack row
        p_id, title, desc, init_msg, claim_msg, role_id, create_cat, claim_cat = row

        role_str = f"<@&{role_id}>" if role_id else "Not Set"
        create_cat_str = f"<#{create_cat}>" if create_cat else "Not Set (Auto-creates root)"
        claim_cat_str = f"<#{claim_cat}>" if claim_cat else "Not Set (Stays in current)"

        content = f"Editing Configuration for **{panel_id}**\n\n"
        content += f"**Initial Message:** {init_msg}\n"
        content += f"**Claimed Message:** {claim_msg}\n"
        content += f"**Ping Role:** {role_str}\n"
        content += f"**Created Category:** {create_cat_str}\n"
        content += f"**Claimed Category:** {claim_cat_str}\n\n"
        content += "Use the dropdown below to modify these settings or delete the panel entirely."

        embed = embed_factory.create_clean_embed(f"⚙️ Panel Config: {panel_id}", content)
        view = ui_tickets.PanelConfigView(self.db_conn, panel_id)
        await ctx.send(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Tickets(bot))
