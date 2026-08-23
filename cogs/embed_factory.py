import discord

def create_clean_embed(title: str = None, description: str = None, color: discord.Color = None, author: discord.Member | discord.User = None, thumbnail_url: str = None, footer_text: str = None) -> discord.Embed:
    if color is None:
        color = discord.Color.from_str("#2B2D31")

    if title and not description:
        description = "## " + str(title)
        title = None
    elif title and description:
        description = "## " + str(title) + "\n\n" + str(description)
        title = None

    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )

    if author:
        embed.set_author(name=author.display_name, icon_url=author.display_avatar.url if author.display_avatar else None)

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    if footer_text:
        embed.set_footer(text=footer_text)

    return embed

def create_meter_embed(author: discord.Member | discord.User, target_id: int, meter_name: str, emoji: str, score: int, progress_bar: str, snark: str) -> discord.Embed:
    embed = create_clean_embed(
        title=f"{emoji} The {meter_name.capitalize()} Meter",
        description=f"**Target:** <@{target_id}>\n**Score:** {score}%\n\n{progress_bar}\n\n-# {snark}",
    )
    embed.set_footer(text=f"Command: !{meter_name} • Used By: {author.display_name}")
    return embed
