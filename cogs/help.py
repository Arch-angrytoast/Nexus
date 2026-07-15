import discord
from discord.ext import commands
from .ui_help import HelpView

class CustomHelpCommand(commands.HelpCommand):
    """We subclass the default help command to tap into its natural mapping logic, but hijack the output."""

    async def send_bot_help(self, mapping):
        # mapping is a dict of Cog: List[Command]
        channel = self.get_destination()

        from . import box_formatter
        box = box_formatter.create_box("Nexus Help Menu", "Welcome to the Nexus help menu! Please select a category from the dropdown below to see the available commands.")

        view = HelpView(self.context.bot, mapping)
        await channel.send(content=box, view=view)

    async def send_cog_help(self, cog):
        await self.send_bot_help(self.context.bot.cogs.items())

    async def send_group_help(self, group):
        await self.send_bot_help(self.context.bot.cogs.items())

    async def send_command_help(self, command):
        await self.send_bot_help(self.context.bot.cogs.items())


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Save the original help command to restore it if this cog unloads
        self._original_help_command = bot.help_command
        # Assign the custom one
        bot.help_command = CustomHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
