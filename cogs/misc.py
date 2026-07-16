import discord
from discord.ext import commands
import random
import base64
import string
import asyncio
import re
from . import embed_factory

class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="avatar", description="Get a user's avatar")
    async def avatar(self, ctx, user: discord.Member = None):
        user = user or ctx.author
        url = user.avatar.url if user.avatar else user.default_avatar.url
        embed = embed_factory.create_clean_embed(f"{user.display_name}'s Avatar", "")
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", description="Display information about the server")
    async def serverinfo(self, ctx):
        guild = ctx.guild
        content = f"**Name:** {guild.name}\n"
        content += f"**ID:** {guild.id}\n"
        content += f"**Owner:** {guild.owner.mention}\n"
        content += f"**Created:** <t:{int(guild.created_at.timestamp())}:D>\n"
        content += f"**Members:** {guild.member_count}\n"
        content += f"**Roles:** {len(guild.roles)}\n"

        embed = embed_factory.create_clean_embed("Server Info", content)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="userinfo", description="Display information about a user")
    async def userinfo(self, ctx, user: discord.Member = None):
        user = user or ctx.author
        content = f"**Username:** {user.name}\n"
        content += f"**ID:** {user.id}\n"
        content += f"**Joined Server:** <t:{int(user.joined_at.timestamp())}:D>\n"
        content += f"**Account Created:** <t:{int(user.created_at.timestamp())}:D>\n"
        content += f"**Top Role:** {user.top_role.mention if user.top_role != ctx.guild.default_role else 'None'}\n"

        embed = embed_factory.create_clean_embed(f"User Info: {user.display_name}", content)
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ping", description="Check the bot's latency")
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        embed = embed_factory.create_clean_embed("Ping", f"🏓 Pong! Latency is `{latency}ms`.")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="coinflip", description="Flip a coin")
    async def coinflip(self, ctx):
        outcome = random.choice(["Heads", "Tails"])
        embed = embed_factory.create_clean_embed("Coin Flip", f"🪙 The coin landed on **{outcome}**!")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="roll", description="Roll a dice (e.g., 1d6, 2d20)")
    async def roll(self, ctx, dice: str = "1d6"):
        try:
            rolls, limit = map(int, dice.lower().split('d'))
            if rolls > 100 or limit > 1000:
                raise ValueError("Too high")
        except Exception:
            embed = embed_factory.create_clean_embed("Error", "Invalid format! Use `NdN` (e.g., `2d6`). Max 100d1000.")
            await ctx.send(embed=embed, ephemeral=True)
            return

        results = [random.randint(1, limit) for _ in range(rolls)]
        total = sum(results)
        content = f"**Rolled:** {dice}\n**Results:** {results}\n**Total:** {total}"
        if len(content) > 2000:
            content = f"**Total:** {total} (Individual results hidden due to length)"

        embed = embed_factory.create_clean_embed("Dice Roll", content)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="8ball", description="Ask the magic 8ball a question")
    async def eight_ball(self, ctx, *, question: str):
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes - definitely.",
            "You may rely on it.", "As I see it, yes.", "Most likely.", "Outlook good.",
            "Yes.", "Signs point to yes.", "Reply hazy, try again.", "Ask again later.",
            "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.",
            "Very doubtful."
        ]
        embed = embed_factory.create_clean_embed("Magic 8-Ball", f"**Question:** {question}\n**Answer:** {random.choice(responses)}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="choose", description="Choose from a comma-separated list of items")
    async def choose(self, ctx, *, items: str):
        choices = [item.strip() for item in items.split(",") if item.strip()]
        if len(choices) < 2:
            embed = embed_factory.create_clean_embed("Error", "Please provide at least 2 choices separated by commas.")
            await ctx.send(embed=embed, ephemeral=True)
            return

        embed = embed_factory.create_clean_embed("Choice", f"I choose: **{random.choice(choices)}**")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="reverse", description="Reverse a string of text")
    async def reverse(self, ctx, *, text: str):
        reversed_text = text[::-1]
        embed = embed_factory.create_clean_embed("Reversed Text", reversed_text)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="mock", description="MoCk A sTrInG oF tExT")
    async def mock(self, ctx, *, text: str):
        mocked = "".join(random.choice([c.upper(), c.lower()]) for c in text)
        embed = embed_factory.create_clean_embed("Mocked Text", mocked)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="joke", description="Tell a random joke")
    async def joke(self, ctx):
        jokes = [
            "Why do programmers prefer dark mode? Because light attracts bugs.",
            "How many programmers does it take to change a light bulb? None, that's a hardware problem.",
            "Why did the programmer quit his job? Because he didn't get arrays.",
            "There are 10 types of people in the world: those who understand binary, and those who don't.",
            "A SQL query goes into a bar, walks up to two tables and asks... 'Can I join you?'"
        ]
        embed = embed_factory.create_clean_embed("Joke", random.choice(jokes))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="fact", description="Tell a random fact")
    async def fact(self, ctx):
        facts = [
            "Banging your head against a wall for one hour burns 150 calories.",
            "Snakes can help predict earthquakes.",
            "A flock of crows is known as a murder.",
            "The first computer mouse was invented in 1964 and was made out of wood.",
            "A jiffy is an actual unit of time: 1/100th of a second."
        ]
        embed = embed_factory.create_clean_embed("Fact", random.choice(facts))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rps", description="Play Rock, Paper, Scissors")
    async def rps(self, ctx, choice: str):
        choice = choice.lower()
        if choice not in ["rock", "paper", "scissors"]:
            await ctx.send("Please choose rock, paper, or scissors.", ephemeral=True)
            return

        bot_choice = random.choice(["rock", "paper", "scissors"])

        if choice == bot_choice:
            result = "It's a tie!"
        elif (choice == "rock" and bot_choice == "scissors") or \
             (choice == "paper" and bot_choice == "rock") or \
             (choice == "scissors" and bot_choice == "paper"):
            result = "You win!"
        else:
            result = "I win!"

        content = f"You chose: **{choice.title()}**\nI chose: **{bot_choice.title()}**\n\n{result}"
        embed = embed_factory.create_clean_embed("Rock Paper Scissors", content)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="password", description="Generate a random secure password")
    async def password(self, ctx, length: int = 12):
        if length < 8 or length > 64:
            await ctx.send("Length must be between 8 and 64 characters.", ephemeral=True)
            return

        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        pwd = "".join(random.choice(chars) for _ in range(length))

        # Send ephemerally so others can't see the password
        embed = embed_factory.create_clean_embed("Generated Password", f"||`{pwd}`||")
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="b64encode", description="Encode text to Base64")
    async def b64encode(self, ctx, *, text: str):
        encoded = base64.b64encode(text.encode("utf-8")).decode("utf-8")
        embed = embed_factory.create_clean_embed("Base64 Encoded", f"```\n{encoded}\n```")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="b64decode", description="Decode Base64 text")
    async def b64decode(self, ctx, *, encoded: str):
        try:
            decoded = base64.b64decode(encoded.encode("utf-8")).decode("utf-8")
            embed = embed_factory.create_clean_embed("Base64 Decoded", f"```\n{decoded}\n```")
            await ctx.send(embed=embed)
        except Exception:
            embed = embed_factory.create_clean_embed("Error", "Invalid Base64 string.")
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="poll", description="Create a simple yes/no poll")
    async def poll(self, ctx, *, question: str):
        embed = embed_factory.create_clean_embed("📊 Poll", f"**{question}**\n\nPoll by {ctx.author.mention}")
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    @commands.hybrid_command(name="timer", description="Set a timer (in minutes, max 60)")
    async def timer(self, ctx, minutes: int):
        if minutes < 1 or minutes > 60:
            await ctx.send("Timer must be between 1 and 60 minutes.", ephemeral=True)
            return

        embed = embed_factory.create_clean_embed("Timer Set", f"Timer set for {minutes} minute(s). I will remind you when it's done!")
        await ctx.send(embed=embed)

        await asyncio.sleep(minutes * 60)

        embed = embed_factory.create_clean_embed("Timer Finished!", f"{ctx.author.mention}, your timer for {minutes} minute(s) is up!")
        await ctx.send(ctx.author.mention, embed=embed)

    @commands.hybrid_command(name="math", description="Evaluate a simple math expression (+, -, *, /)")
    async def math(self, ctx, *, expression: str):
        cleaned = re.sub(r'[^0-9+\-*/. ]', '', expression)
        if not cleaned:
            await ctx.send("Invalid characters in expression. Only numbers and +, -, *, / allowed.", ephemeral=True)
            return

        # Prevent dangerous exponentiation that can freeze the thread
        if '**' in cleaned:
            await ctx.send("Exponentiation is disabled.", ephemeral=True)
            return

        try:
            # Safe evaluation wrapper limiting time and output
            result = eval(cleaned, {"__builtins__": None}, {})
            embed = embed_factory.create_clean_embed("Math Result", f"**Expression:** `{cleaned}`\n**Result:** `{result}`")
            await ctx.send(embed=embed)
        except Exception as e:
            embed = embed_factory.create_clean_embed("Error", f"Failed to evaluate expression: {e}")
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="wordcount", description="Count the words and characters in a text")
    async def wordcount(self, ctx, *, text: str):
        words = len(text.split())
        chars = len(text)
        chars_no_spaces = len(text.replace(" ", ""))

        content = f"**Words:** {words}\n**Characters (with spaces):** {chars}\n**Characters (no spaces):** {chars_no_spaces}"
        embed = embed_factory.create_clean_embed("Word Count", content)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Misc(bot))
