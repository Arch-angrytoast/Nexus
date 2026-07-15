import discord
import sqlite3

class BannedWordsModal(discord.ui.Modal, title='Manage Banned Words'):
    words_input = discord.ui.TextInput(
        label='Banned Words (comma-separated)',
        style=discord.TextStyle.paragraph,
        placeholder='word1, word2, badword3...',
        required=False,
        max_length=2000
    )

    def __init__(self, db_conn: sqlite3.Connection, current_words: str, view_to_refresh):
        super().__init__()
        self.db_conn = db_conn
        self.view_to_refresh = view_to_refresh
        self.words_input.default = current_words

    async def on_submit(self, interaction: discord.Interaction):
        cursor = self.db_conn.cursor()
        clean_words = ", ".join([w.strip().lower() for w in self.words_input.value.split(',') if w.strip()])
        cursor.execute("INSERT OR REPLACE INTO server_config (key, value) VALUES (?, ?)", ("banned_words", clean_words))
        self.db_conn.commit()

        await interaction.response.defer()
        await self.view_to_refresh.refresh_embed(interaction)

class ChannelAssignSelect(discord.ui.ChannelSelect):
    def __init__(self, db_conn: sqlite3.Connection, config_key: str, view_to_refresh):
        self.db_conn = db_conn
        self.config_key = config_key
        self.view_to_refresh = view_to_refresh

        display_name = config_key.replace('_', ' ').title()
        super().__init__(
            placeholder=f"Select the {display_name}...",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text]
        )

    async def callback(self, interaction: discord.Interaction):
        selected_channel = self.values[0]
        cursor = self.db_conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO server_config (key, value) VALUES (?, ?)", (self.config_key, str(selected_channel.id)))
        self.db_conn.commit()

        # Reset the view back to the main dropdown
        self.view_to_refresh.clear_items()
        self.view_to_refresh.add_item(MainSetupDropdown(self.view_to_refresh))

        await interaction.response.defer()
        await self.view_to_refresh.refresh_embed(interaction)

class MainSetupDropdown(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label="Set General Channel", description="Select the channel for English-only rules", emoji="💬", value="general_channel"),
            discord.SelectOption(label="Set Spam Channel", description="Select the channel exempt from spam rules", emoji="🗑️", value="spam_channel"),
            discord.SelectOption(label="Manage Banned Words", description="Edit the server's profanity blacklist", emoji="🛑", value="banned_words")
        ]
        super().__init__(placeholder="Choose an automod setting to configure...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selection = self.values[0]

        if selection == "banned_words":
            cursor = self.parent_view.db_conn.cursor()
            cursor.execute("SELECT value FROM server_config WHERE key = 'banned_words'")
            row = cursor.fetchone()
            current_words = row[0] if row else ""

            modal = BannedWordsModal(self.parent_view.db_conn, current_words, self.parent_view)
            await interaction.response.send_modal(modal)
            # We don't edit the message here, the modal submission will trigger a refresh
        else:
            # Swap out the main dropdown for the channel select
            self.parent_view.clear_items()
            self.parent_view.add_item(ChannelAssignSelect(self.parent_view.db_conn, selection, self.parent_view))

            # Also add a "Cancel" button to go back
            cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
            async def cancel_callback(btn_interaction):
                self.parent_view.clear_items()
                self.parent_view.add_item(MainSetupDropdown(self.parent_view))
                await btn_interaction.response.edit_message(view=self.parent_view)
            cancel_btn.callback = cancel_callback
            self.parent_view.add_item(cancel_btn)

            await interaction.response.edit_message(view=self.parent_view)

class SetupView(discord.ui.View):
    def __init__(self, db_conn: sqlite3.Connection, generate_embed_func):
        super().__init__(timeout=600)
        self.db_conn = db_conn
        self.generate_embed_func = generate_embed_func
        self.add_item(MainSetupDropdown(self))

    async def refresh_embed(self, interaction: discord.Interaction):
        embed = self.generate_embed_func()
        # Reset to main dropdown
        self.clear_items()
        self.add_item(MainSetupDropdown(self))

        try:
            await interaction.edit_original_response(embed=embed, view=self)
        except Exception:
            pass
