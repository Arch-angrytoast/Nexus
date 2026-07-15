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
        await interaction.response.defer()
        cursor = self.db_conn.cursor()
        words_list = [w.strip().lower() for w in self.words_input.value.split(',') if w.strip()]
        clean_words = ", ".join(words_list)
        cursor.execute("INSERT OR REPLACE INTO server_config (key, value) VALUES (?, ?)", ("banned_words", clean_words))
        self.db_conn.commit()

        # Sync with Discord's Native Automod
        guild = interaction.guild
        rule_name = "Nexus Banned Words"

        # Check if the rule already exists
        existing_rules = await guild.fetch_automod_rules()
        nexus_rule = next((r for r in existing_rules if r.name == rule_name), None)

        # Check if filter is globally enabled
        cursor.execute("SELECT value FROM server_config WHERE key = ?", ("filter_words",))
        row = cursor.fetchone()
        is_enabled = row[0] == "1" if row else True

        trigger_metadata = {"keyword_filter": words_list}
        action = discord.AutoModRuleAction(custom_message="Your message was blocked by Nexus because it contained a banned word. You have been issued a warning.")

        try:
            if nexus_rule:
                if words_list:
                    await nexus_rule.edit(trigger_metadata=discord.AutoModTrigger(keyword_filter=words_list), actions=[action], enabled=is_enabled)
                else:
                    await nexus_rule.delete() # Nothing to ban
            elif words_list:
                await guild.create_automod_rule(
                    name=rule_name,
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger_type=discord.AutoModRuleTriggerType.keyword,
                    trigger_metadata=discord.AutoModTrigger(keyword_filter=words_list),
                    actions=[action],
                    enabled=is_enabled,
                    reason="Nexus Automod Dashboard Sync"
                )
        except discord.Forbidden:
            pass # Lacks Manage Server permissions

        await self.view_to_refresh.refresh_embed(interaction)


class FilterToggleView(discord.ui.View):
    def __init__(self, db_conn: sqlite3.Connection, parent_view):
        super().__init__(timeout=600)
        self.db_conn = db_conn
        self.parent_view = parent_view

        self.filters = {
            "filter_links": "🔗 Link/Invite Filter",
            "filter_words": "🤬 Banned Words",
            "filter_english": "🗣️ English-Only",
            "filter_commands": "🤖 Bot Commands",
            "filter_spam": "🗑️ Spam/Velocity",
            "antinuke": "🛡️ Anti-Nuke Protection"
        }

        for key, label in self.filters.items():
            self.add_item(self.create_button(key, label))

        # Back Button
        back_btn = discord.ui.Button(label="Back to Menu", style=discord.ButtonStyle.secondary, row=2)
        async def back_callback(interaction: discord.Interaction):
            self.parent_view.clear_items()
            self.parent_view.add_item(MainSetupDropdown(self.parent_view))
            await interaction.response.edit_message(view=self.parent_view)
        back_btn.callback = back_callback
        self.add_item(back_btn)

    def is_enabled(self, key: str) -> bool:
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT value FROM server_config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] == "1" if row else True

    def create_button(self, key: str, label: str):
        enabled = self.is_enabled(key)
        style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.danger

        btn = discord.ui.Button(label=label, style=style)

        async def btn_callback(interaction: discord.Interaction):
            await interaction.response.defer()
            new_val = "0" if self.is_enabled(key) else "1"
            cursor = self.db_conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO server_config (key, value) VALUES (?, ?)", (key, new_val))
            self.db_conn.commit()

            # If toggling banned words, sync state with Discord
            if key == "filter_words":
                try:
                    guild = interaction.guild
                    existing_rules = await guild.fetch_automod_rules()
                    nexus_rule = next((r for r in existing_rules if r.name == "Nexus Banned Words"), None)
                    if nexus_rule:
                        await nexus_rule.edit(enabled=(new_val == "1"))
                except discord.Forbidden:
                    pass

            # Refresh the buttons
            btn.style = discord.ButtonStyle.success if new_val == "1" else discord.ButtonStyle.danger

            # Also refresh the main embed
            embed = self.parent_view.generate_embed_func()
            try:
                await interaction.edit_original_response(embed=embed, view=self)
            except discord.NotFound:
                pass

        btn.callback = btn_callback
        return btn

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
            discord.SelectOption(label="Manage Banned Words", description="Edit the server's profanity blacklist", emoji="🛑", value="banned_words"),
            discord.SelectOption(label="Toggle Automod/Anti-Nuke", description="Turn specific filters or Anti-Nuke ON/OFF", emoji="⚙️", value="toggles")
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
        elif selection == "toggles":
            self.parent_view.clear_items()
            # We copy all items from FilterToggleView into the parent_view, or just use the parent view
            toggle_view = FilterToggleView(self.parent_view.db_conn, self.parent_view)
            for item in toggle_view.children:
                self.parent_view.add_item(item)
            await interaction.response.edit_message(view=self.parent_view)
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
