with open('cogs/ui_setup.py', 'r') as f:
    content = f.read()

# Replace AutoModTrigger with dict if it doesn't work, wait discord.py 2.3.2 uses discord.AutoModTrigger ? No, earlier I saw AutoModTrigger in the dir list.
