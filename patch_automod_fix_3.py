with open('cogs/automod.py', 'r') as f:
    content = f.read()

# I see, the type hint `discord.AutoModAction` IS correct in terms of existing in the library,
# wait, actually the review said: "discord.AutoModAction does not exist in discord.py (the correct class is discord.AutoModActionExecution)"
# But `hasattr(discord, 'AutoModAction')` is True.
# Oh, it's `AutoModAction` for the action you take, but the event argument is `discord.AutoModActionExecution`? No, wait.
# Let me check discord.py version 2.3.2 documentation using dir
