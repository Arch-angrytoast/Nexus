import re

with open('webserver.py', 'r') as f:
    content = f.read()

# Add a specific route for the bot-invite
old_invite = '''@app.route("/invite")
async def invite():
    return await discord_auth.create_session(scopes=["identify", "bot", "guilds.join"])'''

new_invite = '''@app.route("/invite")
async def invite():
    # Login & Auto-Join Support Server Flow
    return await discord_auth.create_session(scopes=["identify", "guilds.join"])

@app.route("/bot-invite")
async def bot_invite():
    # Add Bot & Auto-Join Support Server Flow
    return await discord_auth.create_session(scopes=["identify", "bot", "guilds.join"])'''

content = content.replace(old_invite, new_invite)

with open('webserver.py', 'w') as f:
    f.write(content)
