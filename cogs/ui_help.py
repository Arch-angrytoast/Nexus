import discord
from discord.ext import commands

class HelpDropdown(discord.ui.Select):
    def __init__(self, bot: commands.Bot, mapping: dict):
        self.bot = bot
        self.mapping = mapping # Dictionary of Cog -> List of Commands

        options = []
        # Add a home option
        options.append(discord.SelectOption(
            label="Home",
            description="Return to the main help menu.",
            emoji="🏠",
            value="home"
        ))

        for cog, cmds in mapping.items():
            if not cmds:
                continue

            cog_name = getattr(cog, 'qualified_name', 'No Category')
            if cog_name == 'StatusCog': # Hide background cogs
                continue

            description = getattr(cog, 'description', f"{len(cmds)} commands")

            # Add some fun emojis based on the cog name
            emoji = "⚙️"
            if "Moderation" in cog_name:
                emoji = "🛡️"
            elif "Automod" in cog_name:
                emoji = "🤖"
            elif "Core" in cog_name:
                emoji = "🎭"

            options.append(discord.SelectOption(
                label=cog_name,
                description=description[:100],
                emoji=emoji,
                value=cog_name
            ))

        super().__init__(placeholder="Select a category to view commands...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "home":
            from . import embed_factory
            embed = embed_factory.create_clean_embed("Nexus Help Menu", "Welcome to the Nexus help menu! Please select a category from the dropdown below to see the available commands.")
            embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user.display_avatar else None)
            await interaction.response.edit_message(embed=embed)
            return

        selected_cog_name = self.values[0]

        # Find the cog object
        target_cog = None
        target_cmds = []
        for cog, cmds in self.mapping.items():
            if getattr(cog, 'qualified_name', 'No Category') == selected_cog_name:
                target_cog = cog
                target_cmds = cmds
                break

        if not target_cmds:
            await interaction.response.send_message("Could not load commands for this category.", ephemeral=True)
            return

        from . import embed_factory
        content = f"*{getattr(target_cog, 'description', '')}*\n\n"

        prefix = self.bot.command_prefix
        if isinstance(prefix, (list, tuple)):
            prefix = prefix[0]

        for cmd in target_cmds:
            # Filter out hidden commands
            if cmd.hidden:
                continue

            # Build signature
            signature = cmd.signature
            if not signature:
                signature = ""

            command_usage = f"`{prefix}{cmd.name} {signature}`".strip()
            command_desc = cmd.description or cmd.short_doc or "No description provided."
            content += f"**{command_usage}**\n{command_desc}\n\n"

        embed = embed_factory.create_clean_embed(f"{selected_cog_name} Commands", content.strip(), footer_text="Parameters wrapped in <> are required, [] are optional.")
        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, mapping: dict):
        super().__init__(timeout=300) # 5 minutes before the dropdown stops working
        self.add_item(HelpDropdown(bot, mapping))
