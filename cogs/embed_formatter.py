import discord
from discord.ui import Container, TextDisplay, Separator, LayoutView
import random
from .snark_pool import STUPID_REPLIES

class MeterView(LayoutView):
    def __init__(self, author: discord.Member | discord.User, target_id: int, meter_name: str, emoji: str, score: int, progress_bar: str, snark: str):
        super().__init__()

        # Build the container with the invisible side color
        container = Container(accent_color=discord.Color.from_str("#2B2D31"))

        # Title section (Using markdown header for emphasis)
        container.add_item(TextDisplay(content=f"## {emoji} The {meter_name.capitalize()} Meter"))
        container.add_item(Separator())

        # Main content
        container.add_item(TextDisplay(content=f"**Target:** <@{target_id}>\n**Score:** {score}%\n\n{progress_bar}"))

        # Snark
        container.add_item(Separator())
        container.add_item(TextDisplay(content=f"*{snark}*"))

        # Footer-like section matching the orbix style
        container.add_item(Separator())
        container.add_item(TextDisplay(content=f"**Command:** `!{meter_name}`\n**Used By:** <@{author.id}>"))

        self.add_item(container)

class InvalidMeterView(LayoutView):
    def __init__(self, author: discord.Member | discord.User):
        super().__init__()

        container = Container(accent_color=discord.Color.from_str("#2B2D31"))
        container.add_item(TextDisplay(content=random.choice(STUPID_REPLIES)))
        container.add_item(Separator())
        container.add_item(TextDisplay(content=f"**Used By:** <@{author.id}>"))

        self.add_item(container)

def create_meter_view(
    author: discord.Member | discord.User,
    target_id: int,
    meter_name: str,
    emoji: str,
    score: int,
    progress_bar: str,
    snark: str
) -> LayoutView:
    return MeterView(author, target_id, meter_name, emoji, score, progress_bar, snark)

def create_invalid_meter_view(author: discord.Member | discord.User) -> LayoutView:
    return InvalidMeterView(author)
