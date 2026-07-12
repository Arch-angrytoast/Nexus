import discord
import random
from .snark_pool import STUPID_REPLIES

def create_meter_embed(
    author: discord.Member | discord.User,
    target_id: int,
    meter_name: str,
    emoji: str,
    score: int,
    progress_bar: str,
    snark: str
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{emoji} The {meter_name.capitalize()} Meter",
        description=f"<@{target_id}> is **{score}%** {meter_name}!\n\n{progress_bar}\n\n*{snark}*",
        color=discord.Color.from_str("#2B2D31")
    )
    embed.set_author(name=author.display_name, icon_url=author.display_avatar.url if author.display_avatar else None)
    return embed

def create_invalid_meter_embed(author: discord.Member | discord.User) -> discord.Embed:
    embed = discord.Embed(
        description=random.choice(STUPID_REPLIES),
        color=discord.Color.from_str("#2B2D31")
    )
    embed.set_author(name=author.display_name, icon_url=author.display_avatar.url if author.display_avatar else None)
    return embed
