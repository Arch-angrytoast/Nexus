# cogs/box_formatter.py
import discord

def create_box(title: str, content: str, command: str = None, used_by: discord.Member | discord.User = None, footer_text: str = None) -> str:
    """
    Creates a clean markdown-based box layout to replace traditional Discord Embeds.
    """
    lines = []

    # Title (using Discord's large header markdown)
    lines.append(f"# {title}")

    # Separator
    lines.append("─────────────────────")

    # Main Content
    lines.append(content)

    # Footer Section (Command / Used By / Extra info)
    has_footer = bool(command or used_by or footer_text)
    if has_footer:
        lines.append("\n─────────────────────")
        if command:
            lines.append(f"**Command:** `{command}`")
        if used_by:
            lines.append(f"**Used By:** <@{used_by.id}>")
        if footer_text:
            lines.append(f"*{footer_text}*")

    return "\n".join(lines)

import random
import random
from .snark_pool import STUPID_REPLIES

def create_meter_box(author, target_id, meter_name, emoji, score, progress_bar, snark):
    title = f"{emoji} The {meter_name.capitalize()} Meter"
    content = f"**Target:** <@{target_id}>\n**Score:** {score}%\n\n{progress_bar}\n\n*{snark}*"
    return create_box(title, content, command=f"!{meter_name}", used_by=author)

def create_invalid_meter_box(author):
    title = "❌ Error"
    content = random.choice(STUPID_REPLIES)
    return create_box(title, content, used_by=author)
