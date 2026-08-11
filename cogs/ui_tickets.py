import discord
from discord.ext import commands
import sqlite3
import datetime
import io
import asyncio
from . import embed_factory

# --- TICKET CREATION LOGIC ---

class TicketManageView(discord.ui.View):
    def __init__(self, db_conn: sqlite3.Connection):
        super().__init__(timeout=None)
        self.db_conn = db_conn

    def check_permissions(self, interaction: discord.Interaction):
        return True

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary, custom_id="tm_claim_btn", emoji="👋")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("Only staff can claim tickets.", ephemeral=True)
            return

        cursor = self.db_conn.cursor()
        cursor.execute("SELECT panel_id FROM tickets WHERE channel_id = ? AND status = 'open'", (interaction.channel.id,))
        row = cursor.fetchone()

        claimed_msg = "Your ticket has been claimed."
        if row:
            panel_id = row[0]
            cursor.execute("SELECT claimed_message, claimed_category_id FROM ticket_panels WHERE panel_id = ?", (panel_id,))
            p_row = cursor.fetchone()
            if p_row:
                if p_row[0]: claimed_msg = p_row[0]
                if p_row[1]:
                    try:
                        cat = interaction.guild.get_channel(int(p_row[1]))
                        if cat and isinstance(cat, discord.CategoryChannel):
                            await interaction.channel.edit(category=cat)
                    except Exception:
                        pass

        embed = embed_factory.create_clean_embed("Ticket Claimed", f"This ticket will be handled by {interaction.user.mention}.\n\n*{claimed_msg}*")
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.secondary, custom_id="tm_unclaim_btn", emoji="🛑")
    async def unclaim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("Only staff can unclaim tickets.", ephemeral=True)
            return

        embed = embed_factory.create_clean_embed("Ticket Unclaimed", "This ticket is now unassigned.")
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Lock", style=discord.ButtonStyle.secondary, custom_id="tm_lock_btn", emoji="🔒")
    async def lock_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("Only staff can lock tickets.", ephemeral=True)
            return

        cursor = self.db_conn.cursor()
        cursor.execute("SELECT user_id FROM tickets WHERE channel_id = ? AND status = 'open'", (interaction.channel.id,))
        row = cursor.fetchone()
        if not row:
            await interaction.response.send_message("Ticket not found.", ephemeral=True)
            return

        member = interaction.guild.get_member(row[0])
        if member:
            await interaction.channel.set_permissions(member, send_messages=False, read_messages=True)

        embed = embed_factory.create_clean_embed("Ticket Locked", "The ticket creator can no longer send messages.")
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Unlock", style=discord.ButtonStyle.secondary, custom_id="tm_unlock_btn", emoji="🔓")
    async def unlock_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("Only staff can unlock tickets.", ephemeral=True)
            return

        cursor = self.db_conn.cursor()
        cursor.execute("SELECT user_id FROM tickets WHERE channel_id = ? AND status = 'open'", (interaction.channel.id,))
        row = cursor.fetchone()
        if not row:
            await interaction.response.send_message("Ticket not found.", ephemeral=True)
            return

        member = interaction.guild.get_member(row[0])
        if member:
            await interaction.channel.set_permissions(member, send_messages=True, read_messages=True)

        embed = embed_factory.create_clean_embed("Ticket Unlocked", "The ticket creator can now send messages.")
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="tm_close_btn", emoji="✖️")
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

        embed = embed_factory.create_clean_embed("Ticket Closed", f"Ticket #{ticket_id} closed by {interaction.user.mention}. Deleting in 5 seconds.")
        await interaction.response.send_message(embed=embed)

        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass

    @discord.ui.button(label="Close + Transcript", style=discord.ButtonStyle.danger, custom_id="tm_close_trans_btn", emoji="📄")
    async def close_with_transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT ticket_id, user_id FROM tickets WHERE channel_id = ? AND status = 'open'", (interaction.channel.id,))
        row = cursor.fetchone()

        if not row:
            await interaction.response.send_message("This does not appear to be an open ticket channel.", ephemeral=True)
            return

        ticket_id, creator_id = row
        cursor.execute("UPDATE tickets SET status = 'closed' WHERE ticket_id = ?", (ticket_id,))
        self.db_conn.commit()

        await interaction.response.defer()

        messages = [message async for message in interaction.channel.history(limit=500, oldest_first=True)]
        transcript = ""
        for msg in messages:
            time_str = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            transcript += f"[{time_str}] {msg.author}: {msg.clean_content}\n"

        file = discord.File(io.BytesIO(transcript.encode('utf-8')), filename=f"transcript_ticket_{ticket_id}.txt")

        creator = interaction.guild.get_member(creator_id)
        if creator:
            try:
                await creator.send(f"Transcript for your ticket #{ticket_id}", file=file)
            except:
                pass

        embed = embed_factory.create_clean_embed("Ticket Closed", f"Ticket #{ticket_id} closed by {interaction.user.mention}. Transcript generated. Deleting in 5 seconds.")
        await interaction.followup.send(embed=embed)

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
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT panel_id, label, ping_role_id, category_id FROM ticket_buttons WHERE button_id = ?", (self.button_id,))
        btn_row = cursor.fetchone()
        if not btn_row:
            await interaction.response.send_message("This ticket type no longer exists.", ephemeral=True)
            return

        panel_id, label, btn_ping, btn_cat = btn_row

        cursor.execute("SELECT initial_message, ping_role_id, created_category_id FROM ticket_panels WHERE panel_id = ?", (panel_id,))
        panel_row = cursor.fetchone()
        p_init_msg, p_ping, p_cat = panel_row if panel_row else ("Support will be with you shortly.", None, None)

        initial_msg = p_init_msg

        role_id = btn_ping or p_ping
        support_role = interaction.guild.get_role(int(role_id)) if role_id else None

        cat_id = btn_cat or p_cat
        category = interaction.guild.get_channel(int(cat_id)) if cat_id else None

        cursor.execute("INSERT INTO tickets (user_id, channel_id, status, created_at, panel_id) VALUES (?, ?, ?, ?, ?)",
                       (interaction.user.id, 0, "open", datetime.datetime.now(datetime.timezone.utc).isoformat(), panel_id))
        self.db_conn.commit()
        ticket_id = cursor.lastrowid

        channel_name = f"ticket-{ticket_id}"

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        await interaction.response.defer(ephemeral=True)

        try:
            ticket_channel = await interaction.guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
            cursor.execute("UPDATE tickets SET channel_id = ? WHERE ticket_id = ?", (ticket_channel.id, ticket_id))
            self.db_conn.commit()

            embed = embed_factory.create_clean_embed(
                f"🎫 {label} Ticket #{ticket_id}",
                f"**Creator:** {interaction.user.mention}\n**Subject:** {self.subject.value}\n\n**Description:**\n{self.description.value}\n\n*{initial_msg}*"
            )

            ping_str = f"{interaction.user.mention}"
            if support_role:
                ping_str += f" {support_role.mention}"

            await ticket_channel.send(content=ping_str, embed=embed, view=TicketManageView(self.db_conn))
            await interaction.followup.send(f"Ticket created: {ticket_channel.mention}", ephemeral=True)
        except Exception as e:
            cursor.execute("DELETE FROM tickets WHERE ticket_id = ?", (ticket_id,))
            self.db_conn.commit()
            await interaction.followup.send(f"Failed to create ticket: {e}", ephemeral=True)


class PublishedTicketButton(discord.ui.Button):
    def __init__(self, db_conn, btn_id, label, emoji, panel_id):
        super().__init__(style=discord.ButtonStyle.secondary, label=label, emoji=emoji, custom_id=f"pub_ticket_{btn_id}_{panel_id}")
        self.db_conn = db_conn
        self.btn_id = btn_id
        self.panel_id = panel_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(UserTicketModal(self.db_conn, self.btn_id))


class PublishedPanelView(discord.ui.View):
    def __init__(self, db_conn: sqlite3.Connection, panel_id: str = "default"):
        super().__init__(timeout=None)
        self.db_conn = db_conn
        self.panel_id = panel_id

        cursor = db_conn.cursor()
        cursor.execute("SELECT button_id, label, emoji FROM ticket_buttons WHERE panel_id = ?", (panel_id,))
        for btn_id, label, emoji in cursor.fetchall():
            self.add_item(PublishedTicketButton(db_conn, btn_id, label, emoji, panel_id))


# --- TICKET BUILDER (setup-tickets) ---

class AddButtonModal(discord.ui.Modal, title="Add Ticket Type"):
    btn_label = discord.ui.TextInput(label="Button Label (e.g. Support)", max_length=30)
    btn_emoji = discord.ui.TextInput(label="Emoji (Optional)", required=False, max_length=10)

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute(
            "INSERT INTO ticket_buttons (panel_id, label, emoji) VALUES (?, ?, ?)",
            (self.parent_view.panel_id, self.btn_label.value, self.btn_emoji.value or None)
        )
        self.parent_view.db_conn.commit()

        # Get the inserted button ID to configure role/category
        cursor.execute("SELECT last_insert_rowid()")
        btn_id = cursor.fetchone()[0]

        await interaction.response.edit_message(embed=embed_factory.create_clean_embed("Configure Additional Settings", "Select specific role or category if needed."), view=ButtonConfigView(self.parent_view, btn_id))


class EditButtonModal(discord.ui.Modal, title="Edit Ticket Type"):
    btn_label = discord.ui.TextInput(label="Button Label (e.g. Support)", max_length=30)
    btn_emoji = discord.ui.TextInput(label="Emoji (Optional)", required=False, max_length=10)

    def __init__(self, parent_view, button_id, current_data):
        super().__init__()
        self.parent_view = parent_view
        self.button_id = button_id

        self.btn_label.default = current_data[0]
        self.btn_emoji.default = current_data[1] or ""

    async def on_submit(self, interaction: discord.Interaction):
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute(
            "UPDATE ticket_buttons SET label=?, emoji=? WHERE button_id=?",
            (self.btn_label.value, self.btn_emoji.value or None, self.button_id)
        )
        self.parent_view.db_conn.commit()
        await interaction.response.edit_message(embed=embed_factory.create_clean_embed("Configure Additional Settings", "Select specific role or category if needed."), view=ButtonConfigView(self.parent_view, self.button_id))

class ButtonRoleSelect(discord.ui.RoleSelect):
    def __init__(self, parent_view, button_id):
        self.parent_view = parent_view
        self.button_id = button_id
        super().__init__(placeholder="Select specific ping role (Optional)")

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute("UPDATE ticket_buttons SET ping_role_id = ? WHERE button_id = ?", (str(role.id), self.button_id))
        self.parent_view.db_conn.commit()
        await interaction.response.send_message(f"Saved role {role.mention} for this button.", ephemeral=True)

class ButtonCategorySelect(discord.ui.ChannelSelect):
    def __init__(self, parent_view, button_id):
        self.parent_view = parent_view
        self.button_id = button_id
        super().__init__(placeholder="Select specific category (Optional)", channel_types=[discord.ChannelType.category])

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute("UPDATE ticket_buttons SET category_id = ? WHERE button_id = ?", (str(cat.id), self.button_id))
        self.parent_view.db_conn.commit()
        await interaction.response.send_message(f"Saved category {cat.mention} for this button.", ephemeral=True)

class ButtonConfigView(discord.ui.View):
    def __init__(self, builder_view, button_id):
        super().__init__(timeout=600)
        self.db_conn = builder_view.db_conn
        self.builder_view = builder_view
        self.button_id = button_id

        self.add_item(ButtonRoleSelect(builder_view, button_id))
        self.add_item(ButtonCategorySelect(builder_view, button_id))

        back_btn = discord.ui.Button(label="Done / Back to Builder", style=discord.ButtonStyle.secondary)
        async def back_callback(interaction: discord.Interaction):
            await self.builder_view.refresh(interaction)
        back_btn.callback = back_callback
        self.add_item(back_btn)

class BuilderButtonActionSelect(discord.ui.Select):
    def __init__(self, parent_view, options, action_type):
        self.parent_view = parent_view
        self.action_type = action_type
        super().__init__(placeholder=f"Select a button to {action_type}...", options=options, custom_id=f"sel_{action_type}_{parent_view.panel_id}")

    async def callback(self, interaction: discord.Interaction):
        btn_id = self.values[0]
        if self.action_type == "delete":
            cursor = self.parent_view.db_conn.cursor()
            cursor.execute("DELETE FROM ticket_buttons WHERE button_id = ?", (btn_id,))
            self.parent_view.db_conn.commit()
            await self.parent_view.refresh(interaction)
        elif self.action_type == "edit":
            cursor = self.parent_view.db_conn.cursor()
            cursor.execute("SELECT label, emoji, ping_role_id, category_id FROM ticket_buttons WHERE button_id = ?", (btn_id,))
            row = cursor.fetchone()
            if row:
                await interaction.response.send_modal(EditButtonModal(self.parent_view, btn_id, row))

class EditPanelTextModal(discord.ui.Modal, title="Edit Panel Text"):
    p_title = discord.ui.TextInput(label="Title")
    p_desc = discord.ui.TextInput(label="Description", style=discord.TextStyle.long)

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

        cursor = self.parent_view.db_conn.cursor()
        cursor.execute("SELECT title, description FROM ticket_panels WHERE panel_id = ?", (self.parent_view.panel_id,))
        row = cursor.fetchone()
        self.p_title.default = row[0] if row else "Support Tickets"
        self.p_desc.default = row[1] if row else "Select a category below."

    async def on_submit(self, interaction: discord.Interaction):
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute("UPDATE ticket_panels SET title=?, description=? WHERE panel_id=?",
                       (self.p_title.value, self.p_desc.value, self.parent_view.panel_id))
        self.parent_view.db_conn.commit()
        await self.parent_view.refresh(interaction)


class TicketBuilderView(discord.ui.View):
    def __init__(self, db_conn: sqlite3.Connection, panel_id: str):
        super().__init__(timeout=600)
        self.db_conn = db_conn
        self.panel_id = panel_id

    def build_preview_embed(self):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT title, description FROM ticket_panels WHERE panel_id = ?", (self.panel_id,))
        row = cursor.fetchone()
        title = row[0] if row else f"{self.panel_id.title()} Tickets"
        desc = row[1] if row else "Select a category below."

        embed = embed_factory.create_clean_embed(f"[PREVIEW] {title}", desc)

        cursor.execute("SELECT button_id, label, emoji, ping_role_id, category_id FROM ticket_buttons WHERE panel_id = ?", (self.panel_id,))
        btns = cursor.fetchall()
        if btns:
            info = ""
            for b_id, lbl, emj, r_id, c_id in btns:
                info += f"• {emj or ''} **{lbl}** (Role: {r_id or 'Panel Default'}, Cat: {c_id or 'Panel Default'})\n"
            embed.add_field(name="Configured Buttons", value=info, inline=False)
        else:
            embed.add_field(name="Configured Buttons", value="None yet. Click 'Add Button'.", inline=False)

        return embed

    async def refresh(self, interaction: discord.Interaction):
        self.clear_items()

        # Add core builder buttons
        self.add_item(discord.ui.Button(label="Edit Panel Text", style=discord.ButtonStyle.primary, custom_id=f"tb_edit_text_{self.panel_id}"))
        self.add_item(discord.ui.Button(label="Add Button", style=discord.ButtonStyle.success, custom_id=f"tb_add_btn_{self.panel_id}"))
        self.add_item(discord.ui.Button(label="Publish Panel", style=discord.ButtonStyle.danger, custom_id=f"tb_publish_{self.panel_id}"))

        cursor = self.db_conn.cursor()
        cursor.execute("SELECT button_id, label FROM ticket_buttons WHERE panel_id = ?", (self.panel_id,))
        btns = cursor.fetchall()
        if btns:
            opts_del = [discord.SelectOption(label=f"Delete: {lbl}", value=str(b_id)) for b_id, lbl in btns[:25]]
            opts_edit = [discord.SelectOption(label=f"Edit: {lbl}", value=str(b_id)) for b_id, lbl in btns[:25]]
            self.add_item(BuilderButtonActionSelect(self, opts_edit, "edit"))
            self.add_item(BuilderButtonActionSelect(self, opts_del, "delete"))

        embed = self.build_preview_embed()

        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction):
        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("tb_edit_text_"):
            await interaction.response.send_modal(EditPanelTextModal(self))
            return False
        elif custom_id.startswith("tb_add_btn_"):
            await interaction.response.send_modal(AddButtonModal(self))
            return False
        elif custom_id.startswith("tb_publish_"):
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT title, description FROM ticket_panels WHERE panel_id = ?", (self.panel_id,))
            row = cursor.fetchone()
            title = row[0] if row else "Support Tickets"
            desc = row[1] if row else "Select a category below."
            embed = embed_factory.create_clean_embed(title, desc)
            view = PublishedPanelView(self.db_conn, self.panel_id)
            await interaction.channel.send(embed=embed, view=view)
            await interaction.response.send_message("Panel published to this channel!", ephemeral=True)
            return False
        return True


# --- PANEL CONFIG (/ticket-config) ---

class PanelConfigMessageModal(discord.ui.Modal, title="Edit Panel Message"):
    def __init__(self, parent_view, key, current_val):
        super().__init__()
        self.parent_view = parent_view
        self.key = key
        self.val_input = discord.ui.TextInput(label="New Value", default=current_val, style=discord.TextStyle.long)
        self.add_item(self.val_input)

    async def on_submit(self, interaction: discord.Interaction):
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute(f"UPDATE ticket_panels SET {self.key} = ? WHERE panel_id = ?", (self.val_input.value, self.parent_view.panel_id))
        self.parent_view.db_conn.commit()
        await self.parent_view.refresh(interaction)

class PanelConfigRoleSelect(discord.ui.RoleSelect):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        super().__init__(placeholder="Select Ping Role")

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute("UPDATE ticket_panels SET ping_role_id = ? WHERE panel_id = ?", (str(role.id), self.parent_view.panel_id))
        self.parent_view.db_conn.commit()
        await self.parent_view.refresh(interaction)

class PanelConfigCategorySelect(discord.ui.ChannelSelect):
    def __init__(self, parent_view, key):
        self.parent_view = parent_view
        self.key = key
        super().__init__(placeholder="Select Category", channel_types=[discord.ChannelType.category])

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute(f"UPDATE ticket_panels SET {self.key} = ? WHERE panel_id = ?", (str(cat.id), self.parent_view.panel_id))
        self.parent_view.db_conn.commit()
        await self.parent_view.refresh(interaction)

class PanelConfigDropdown(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        opts = [
            discord.SelectOption(label="Initial Message", value="initial_message", description="Message sent when ticket opens"),
            discord.SelectOption(label="Claimed Message", value="claimed_message", description="Message appended when claimed"),
            discord.SelectOption(label="Ping Role ID", value="ping_role_id", description="Role ID pinged automatically"),
            discord.SelectOption(label="Created Category ID", value="created_category_id", description="Where new tickets spawn"),
            discord.SelectOption(label="Claimed Category ID", value="claimed_category_id", description="Where claimed tickets move")
        ]
        super().__init__(placeholder="Select a setting to edit...", options=opts)

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        cursor = self.parent_view.db_conn.cursor()
        cursor.execute(f"SELECT {key} FROM ticket_panels WHERE panel_id = ?", (self.parent_view.panel_id,))
        row = cursor.fetchone()
        current_val = row[0] if row and row[0] else ""

        if "message" in key:
            await interaction.response.send_modal(PanelConfigMessageModal(self.parent_view, key, current_val))
        else:
            view = discord.ui.View(timeout=600)
            if key == "ping_role_id":
                view.add_item(PanelConfigRoleSelect(self.parent_view))
            else:
                view.add_item(PanelConfigCategorySelect(self.parent_view, key))

            back_btn = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary)
            async def back_callback(interaction: discord.Interaction):
                await self.parent_view.refresh(interaction)
            back_btn.callback = back_callback
            view.add_item(back_btn)

            embed = embed_factory.create_clean_embed(f"Editing {key.replace('_id', '').replace('_', ' ').title()}", "Use the dropdown below to select.")
            await interaction.response.edit_message(embed=embed, view=view)

class PanelConfigView(discord.ui.View):
    def __init__(self, db_conn, panel_id):
        super().__init__(timeout=600)
        self.db_conn = db_conn
        self.panel_id = panel_id
        self.add_item(PanelConfigDropdown(self))
        self.add_item(discord.ui.Button(label="Delete Entire Panel", style=discord.ButtonStyle.danger, custom_id=f"del_panel_{panel_id}"))

    async def refresh(self, interaction: discord.Interaction):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT * FROM ticket_panels WHERE panel_id = ?", (self.panel_id,))
        row = cursor.fetchone()

        if not row:
            self.clear_items()
            await interaction.response.edit_message(content="Panel no longer exists.", embed=None, view=self)
            return

        p_id, title, desc, init_msg, claim_msg, role_id, create_cat, claim_cat = row

        role_str = f"<@&{role_id}>" if role_id else "Not Set"
        create_cat_str = f"<#{create_cat}>" if create_cat else "Not Set (Auto-creates root)"
        claim_cat_str = f"<#{claim_cat}>" if claim_cat else "Not Set (Stays in current)"

        content = f"Editing Configuration for **{self.panel_id}**\n\n"
        content += f"**Initial Message:** {init_msg}\n"
        content += f"**Claimed Message:** {claim_msg}\n"
        content += f"**Ping Role:** {role_str}\n"
        content += f"**Created Category:** {create_cat_str}\n"
        content += f"**Claimed Category:** {claim_cat_str}\n\n"
        content += "Use the dropdown below to modify these settings or delete the panel entirely."

        embed = embed_factory.create_clean_embed(f"⚙️ Panel Config: {self.panel_id}", content)

        self.clear_items()
        self.add_item(PanelConfigDropdown(self))
        self.add_item(discord.ui.Button(label="Delete Entire Panel", style=discord.ButtonStyle.danger, custom_id=f"del_panel_{self.panel_id}"))

        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction):
        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("del_panel_"):
            cursor = self.db_conn.cursor()
            cursor.execute("DELETE FROM ticket_panels WHERE panel_id = ?", (self.panel_id,))
            cursor.execute("DELETE FROM ticket_buttons WHERE panel_id = ?", (self.panel_id,))
            self.db_conn.commit()
            await interaction.response.send_message(f"Panel `{self.panel_id}` and all its buttons have been deleted.", ephemeral=True)
            self.clear_items()
            await interaction.edit_original_response(view=self)
            return False
        return True
