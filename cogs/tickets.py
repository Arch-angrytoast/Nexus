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
        self.bot.add_view(ui_tickets.PublishedPanelView(self.db_conn))
        self.bot.add_view(ui_tickets.TicketManageView(self.db_conn))

    @commands.hybrid_command(name="ticket-setup", description="[ADMIN] Open the Ticket Panel Builder")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx: commands.Context):
        view = ui_tickets.TicketBuilderView(self.db_conn)
        embed = view.build_preview_embed()

        # Add buttons manually just for the first send
        view.add_item(discord.ui.Button(label="Edit Text", style=discord.ButtonStyle.primary, custom_id="tb_edit_text"))
        view.add_item(discord.ui.Button(label="Add Button", style=discord.ButtonStyle.success, custom_id="tb_add_btn"))
        view.add_item(discord.ui.Button(label="Publish Panel", style=discord.ButtonStyle.danger, custom_id="tb_publish"))

        cursor = self.db_conn.cursor()
        cursor.execute("SELECT button_id, label FROM ticket_buttons WHERE panel_id = 'default'")
        btns = cursor.fetchall()
        if btns:
            opts = [discord.SelectOption(label=f"Delete: {lbl}", value=str(b_id)) for b_id, lbl in btns[:25]]
            view.add_item(ui_tickets.BuilderButtonDeleteSelect(view, opts))

        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name="ticket-config", description="[ADMIN] Configure global ticket settings")
    @commands.has_permissions(administrator=True)
    async def ticket_config(self, ctx: commands.Context):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT key, value FROM ticket_config")
        config = dict(cursor.fetchall())

        cat_id = config.get("default_category")
        role_id = config.get("default_support_role")
        msg = config.get("default_initial_message", "Support will be with you shortly.")

        cat_str = f"<#{cat_id}>" if cat_id else "Not Set (Auto-creates category)"
        role_str = f"<@&{role_id}>" if role_id else "Not Set"

        content = "Use the dropdown to edit global ticket variables (These apply if a specific button doesn't have an override).\n\n"
        content += f"**Default Category:** {cat_str}\n"
        content += f"**Default Support Role:** {role_str}\n"
        content += f"**Default Initial Message:** {msg}"

        embed = embed_factory.create_clean_embed("⚙️ Global Ticket Config", content)
        view = ui_tickets.GlobalConfigView(self.db_conn)
        await ctx.send(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Tickets(bot))
