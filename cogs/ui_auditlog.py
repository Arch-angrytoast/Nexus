import discord
import sqlite3

class AuditConfigView(discord.ui.View):
    def __init__(self, db_conn, guild_id):
        super().__init__(timeout=600)
        self.db_conn = db_conn
        self.guild_id = guild_id

        self.add_item(AuditTypeSelect(self))
        self.add_item(discord.ui.Button(label="Auto-Generate Channels", style=discord.ButtonStyle.success, custom_id=f"auto_gen_audit_{guild_id}"))

    def build_embed(self, row):
        msg_ch = f"<#{row[0]}>" if row[0] else "Not Set"
        mem_ch = f"<#{row[1]}>" if row[1] else "Not Set"
        srv_ch = f"<#{row[2]}>" if row[2] else "Not Set"
        voc_ch = f"<#{row[3]}>" if row[3] else "Not Set"

        from . import embed_factory
        desc = (
            f"**💬 Message Logs:** {msg_ch}\n"
            f"**👥 Member Logs:** {mem_ch}\n"
            f"**🏢 Server Logs:** {srv_ch}\n"
            f"**🎙️ Voice Logs:** {voc_ch}\n\n"
            "Use the dropdown below to configure a channel, or click Auto-Generate."
        )
        return embed_factory.create_clean_embed("⚙️ Audit Log Configuration", desc)

    async def refresh(self, interaction: discord.Interaction):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT message_channel, member_channel, server_channel, voice_channel FROM audit_log_config WHERE guild_id = ?", (str(self.guild_id),))
        row = cursor.fetchone()
        embed = self.build_embed(row)

        # Reset items
        self.clear_items()
        self.add_item(AuditTypeSelect(self))
        self.add_item(discord.ui.Button(label="Auto-Generate Channels", style=discord.ButtonStyle.success, custom_id=f"auto_gen_audit_{self.guild_id}"))

        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction):
        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("auto_gen_audit_"):
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            # Create Category
            cat = await guild.create_category("Logs")

            # Create Channels
            msg_c = await cat.create_text_channel("message-logs")
            mem_c = await cat.create_text_channel("member-logs")
            srv_c = await cat.create_text_channel("server-logs")
            voc_c = await cat.create_text_channel("voice-logs")

            # Save to DB
            cursor = self.db_conn.cursor()
            cursor.execute('''
                UPDATE audit_log_config
                SET message_channel = ?, member_channel = ?, server_channel = ?, voice_channel = ?
                WHERE guild_id = ?
            ''', (str(msg_c.id), str(mem_c.id), str(srv_c.id), str(voc_c.id), str(self.guild_id)))
            self.db_conn.commit()

            # Refresh
            cursor.execute("SELECT message_channel, member_channel, server_channel, voice_channel FROM audit_log_config WHERE guild_id = ?", (str(self.guild_id),))
            row = cursor.fetchone()
            embed = self.build_embed(row)
            await interaction.edit_original_response(embed=embed, view=self)
            return False
        return True


class AuditTypeSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        opts = [
            discord.SelectOption(label="Message Logs", value="message_channel", description="Deletes, Edits, etc.", emoji="💬"),
            discord.SelectOption(label="Member Logs", value="member_channel", description="Joins, Leaves, Bans, Updates", emoji="👥"),
            discord.SelectOption(label="Server Logs", value="server_channel", description="Channels, Roles, Server settings", emoji="🏢"),
            discord.SelectOption(label="Voice Logs", value="voice_channel", description="Joins, Leaves, Moves", emoji="🎙️")
        ]
        super().__init__(placeholder="Select log type to configure...", options=opts)

    async def callback(self, interaction: discord.Interaction):
        log_type = self.values[0]

        # Switch to channel select view
        view = discord.ui.View(timeout=600)
        view.add_item(AuditChannelSelect(self.parent_view, log_type))

        # Add back button
        back_btn = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary)
        async def back_callback(interaction: discord.Interaction):
            await self.parent_view.refresh(interaction)
        back_btn.callback = back_callback
        view.add_item(back_btn)

        from . import embed_factory
        embed = embed_factory.create_clean_embed(f"Select Channel for {log_type.replace('_channel', '').title()} Logs", "Use the dropdown below to select the channel.")

        await interaction.response.edit_message(embed=embed, view=view)


class AuditChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, parent_view, log_type):
        self.parent_view = parent_view
        self.log_type = log_type
        super().__init__(placeholder="Select a channel...", channel_types=[discord.ChannelType.text])

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute(f"UPDATE audit_log_config SET {self.log_type} = ? WHERE guild_id = ?", (str(channel.id), str(self.parent_view.guild_id)))
        self.parent_view.db_conn.commit()

        await self.parent_view.refresh(interaction)
