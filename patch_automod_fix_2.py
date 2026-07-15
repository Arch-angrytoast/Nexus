with open('cogs/automod.py', 'r') as f:
    content = f.read()

# Ah, in discord.py 2.0+ it is called AutoModAction
# Let's check the API docs quickly. No, wait.
# It's `on_automod_action(execution: discord.AutoModAction)` - wait, `discord.py` calls the event `on_automod_action` but the type is `discord.AutoModAction`
