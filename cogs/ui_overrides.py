import discord
import sqlite3
from datetime import datetime, timezone

class ScoreEditModal(discord.ui.Modal, title='Edit User Score'):
    score_input = discord.ui.TextInput(
        label='New Score (0-100)',
        style=discord.TextStyle.short,
        placeholder='e.g., 99',
        required=True,
        max_length=3
    )

    def __init__(self, db_conn: sqlite3.Connection, target: discord.Member, meter_name: str, view_to_refresh):
        super().__init__()
        self.db_conn = db_conn
        self.target = target
        self.meter_name = meter_name
        self.view_to_refresh = view_to_refresh
        self.title = f"Edit '{meter_name}' for {target.display_name}"[:45]

    async def on_submit(self, interaction: discord.Interaction):
        try:
            score = int(self.score_input.value)
            if score < 0 or score > 100:
                await interaction.response.send_message("Score must be between 0 and 100.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("Score must be a valid integer.", ephemeral=True)
            return

        utc_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        cursor = self.db_conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO score_overrides (target_id, meter_name, utc_date, score) VALUES (?, ?, ?, ?)",
            (self.target.id, self.meter_name, utc_date, score)
        )
        self.db_conn.commit()

        await interaction.response.defer()
        await self.view_to_refresh.update_embed(interaction)

class MeterSelect(discord.ui.Select):
    def __init__(self, meters: list[str], view):
        self.parent_view = view
        options = [discord.SelectOption(label=meter, value=meter) for meter in meters[:25]] # Discord limit is 25
        super().__init__(placeholder="Select a meter to edit...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        meter_name = self.values[0]
        modal = ScoreEditModal(
            db_conn=self.parent_view.db_conn,
            target=self.parent_view.target,
            meter_name=meter_name,
            view_to_refresh=self.parent_view
        )
        await interaction.response.send_modal(modal)

class OverrideView(discord.ui.View):
    def __init__(self, db_conn: sqlite3.Connection, target: discord.Member, meters: list[str], generate_embed_func):
        super().__init__(timeout=300) # 5 minutes timeout
        self.db_conn = db_conn
        self.target = target
        self.meters = meters
        self.generate_embed_func = generate_embed_func

        if meters:
            self.add_item(MeterSelect(meters, self))

    async def update_embed(self, interaction: discord.Interaction):
        box = self.generate_embed_func()
        try:
            await interaction.edit_original_response(content=box, embed=None, view=self)
        except Exception:
            pass # Failsafe if interaction expired

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.update_embed(interaction)

    @discord.ui.button(label="Clear Overrides", style=discord.ButtonStyle.danger, row=1)
    async def clear_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        utc_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        cursor = self.db_conn.cursor()
        cursor.execute("DELETE FROM score_overrides WHERE target_id = ? AND utc_date = ?", (self.target.id, utc_date))
        self.db_conn.commit()

        await interaction.response.defer()
        await self.update_embed(interaction)
