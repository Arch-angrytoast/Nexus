import re

with open('cogs/tickets.py', 'r') as f:
    content = f.read()

# Replace static category/overwrites logic with dynamic DB fetching
# Also remove the basic setup-tickets and replace with two commands

new_logic = """
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
                f"**Created By:** {interaction.user.mention}\\n**Subject:** {self.subject.value}\\n\\n**Description:**\\n{self.description.value}\\n\\n*Support will be with you shortly.*",
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
"""

# Replace the specific block in the file
content = re.sub(r'    async def on_submit\(self, interaction: discord\.Interaction\):.*?(?=\nclass OpenTicketView)', new_logic, content, flags=re.DOTALL)


commands_logic = """
    @commands.hybrid_command(name="setup-tickets-config", description="[ADMIN] Configure the ticket system settings")
    @commands.has_permissions(administrator=True)
    async def setup_tickets_config(self, ctx: commands.Context):
        from . import ui_tickets
        def generate_setup_embed():
            cursor = self.bot.db_conn.cursor()
            cursor.execute("SELECT key, value FROM ticket_config")
            config = dict(cursor.fetchall())

            title = config.get("panel_title", "🎫 Support Tickets")
            desc = config.get("panel_desc", "Click the button below to open a private support ticket.")
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
        desc = config.get("panel_desc", "Click the button below to open a private support ticket.\\n\\nPlease be prepared to provide a detailed description of your issue so our staff can assist you promptly.")

        embed = embed_factory.create_clean_embed(title, desc)
        view = OpenTicketView(self.db_conn)
        await ctx.send(embed=embed, view=view)
        if ctx.message:
            try:
                await ctx.message.delete()
            except:
                pass
"""

content = re.sub(r'    @commands\.hybrid_command\(name="setup-tickets".*', commands_logic, content, flags=re.DOTALL)

with open('cogs/tickets.py', 'w') as f:
    f.write(content)
