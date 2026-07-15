import discord
from discord.ext import commands
from discord import app_commands
import datetime

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="kick", description="Kick a user from the server")
    @app_commands.describe(member="The member to kick", reason="The reason for the kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("You cannot kick someone with an equal or higher role than you.", ephemeral=True)
            return

        try:
            await member.kick(reason=reason)
            embed = discord.Embed(
                title="User Kicked",
                description=f"**{member.display_name}** has been kicked.\n**Reason:** {reason}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I do not have permission to kick this user. Make sure my role is higher than theirs.", ephemeral=True)

    @commands.hybrid_command(name="ban", description="Ban a user from the server")
    @app_commands.describe(member="The member to ban", reason="The reason for the ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("You cannot ban someone with an equal or higher role than you.", ephemeral=True)
            return

        try:
            await member.ban(reason=reason)
            embed = discord.Embed(
                title="User Banned",
                description=f"**{member.display_name}** has been banned.\n**Reason:** {reason}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I do not have permission to ban this user. Make sure my role is higher than theirs.", ephemeral=True)

    @commands.hybrid_command(name="unban", description="Unban a user by their user ID")
    @app_commands.describe(user_id="The ID of the user to unban")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: str):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user)
            embed = discord.Embed(
                title="User Unbanned",
                description=f"**{user.display_name}** has been unbanned.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except ValueError:
            await ctx.send("Please provide a valid numeric User ID.", ephemeral=True)
        except discord.NotFound:
            await ctx.send("User is not banned or could not be found.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("I do not have permission to unban users.", ephemeral=True)

    @commands.hybrid_command(name="purge", aliases=["clear"], description="Delete a number of messages in the channel")
    @app_commands.describe(amount="The number of messages to delete (max 100)")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int):
        if amount < 1 or amount > 100:
            await ctx.send("Please provide a number between 1 and 100.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)
        try:
            # Add 1 to account for the command message if it was a prefix command
            deleted = await ctx.channel.purge(limit=amount + 1 if ctx.interaction is None else amount)
            await ctx.send(f"Successfully deleted {len(deleted)} messages.", delete_after=5, ephemeral=True)
        except discord.Forbidden:
            await ctx.send("I do not have permission to manage messages.", ephemeral=True)
        except discord.HTTPException:
            await ctx.send("Failed to delete messages. Messages older than 14 days cannot be bulk deleted.", ephemeral=True)

    @commands.hybrid_command(name="timeout", description="Timeout a user for a specified duration")
    @app_commands.describe(member="The member to timeout", minutes="Duration in minutes", reason="The reason for the timeout")
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, member: discord.Member, minutes: int, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("You cannot timeout someone with an equal or higher role than you.", ephemeral=True)
            return

        if minutes < 1 or minutes > 40320: # Discord max is 28 days
            await ctx.send("Timeout duration must be between 1 and 40,320 minutes (28 days).", ephemeral=True)
            return

        duration = datetime.timedelta(minutes=minutes)
        try:
            await member.timeout(duration, reason=reason)
            embed = discord.Embed(
                title="User Timed Out",
                description=f"**{member.display_name}** has been timed out for {minutes} minutes.\n**Reason:** {reason}",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I do not have permission to timeout this user.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
