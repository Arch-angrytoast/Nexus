import os
import sqlite3
import asyncio
from quart import Quart, redirect, url_for, render_template, request, send_from_directory
from quart_discord import DiscordOAuth2Session, requires_authorization, Unauthorized
from dotenv import load_dotenv

load_dotenv()

app = Quart(__name__)
app.secret_key = os.getenv("QUART_SECRET_KEY", os.urandom(32))
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true" # For testing locally

app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
app.config["DISCORD_REDIRECT_URI"] = os.getenv("OAUTH_REDIRECT_URI", "http://78.154.103.22:12166/callback")

SUPPORT_SERVER_ID = 1519633747559841844

try:
    discord_auth = DiscordOAuth2Session(app)
except Exception as e:
    print(f"Failed to initialize Discord OAuth (Missing creds?): {e}")
    discord_auth = None

def get_db():
    conn = sqlite3.connect('bot_data.db')
    conn.row_factory = sqlite3.Row
    return conn

async def is_authorized():
    try:
        # 1. Check if user is the Bot Owner
        user = await discord_auth.fetch_user()
        if str(user.id) == os.getenv("OWNER_ID"):
            return True

        # 2. Check if user has "Manage Server" or "Administrator" in the specific Project Nexus Server
        user_guilds = await discord_auth.fetch_guilds()
        for g in user_guilds:
            if g.id == SUPPORT_SERVER_ID:
                is_admin = getattr(g.permissions, 'administrator', False)
                can_manage = getattr(g.permissions, 'manage_guild', False)
                # Fallback to bitwise check if getattr fails for some reason
                if not is_admin and not can_manage:
                    try:
                        perms_val = int(g.permissions.value)
                        is_admin = (perms_val & 0x8) == 0x8
                        can_manage = (perms_val & 0x20) == 0x20
                    except:
                        pass

                if is_admin or can_manage:
                    return True

        return False
    except Exception as e:
        print(f"Auth error: {e}")
        return False

@app.route("/")
async def index():
    user = None
    if discord_auth and await discord_auth.authorized:
        user = await discord_auth.fetch_user()
    return await render_template('landing.html', user=user)

@app.route("/login", strict_slashes=False)
async def login():
    if not discord_auth:
        return "Discord OAuth not configured", 500
    return await discord_auth.create_session(scope=["identify", "guilds"])

@app.route("/invite", strict_slashes=False)
async def invite():
    if not discord_auth:
        return "Discord OAuth not configured", 500
    return await discord_auth.create_session(scope=["identify", "guilds", "guilds.join"])

@app.route("/bot-invite", strict_slashes=False)
async def bot_invite():
    if not discord_auth:
        return "Discord OAuth not configured", 500
    return await discord_auth.create_session(scope=["identify", "guilds", "bot", "guilds.join"])

@app.route("/callback", strict_slashes=False)
async def callback():
    if not discord_auth:
        return "Discord OAuth not configured", 500
    try:
        await discord_auth.callback()

        # Determine where to redirect based on scopes
        token_info = await discord_auth.get_authorization_token()
        scopes = token_info.get("scope", "").split()

        if "guilds.join" in scopes:
            # They came from /invite, add them to the support server
            user = await discord_auth.fetch_user()
            bot_token = os.getenv("DISCORD_TOKEN")
            access_token = token_info.get("access_token")

            if bot_token and access_token:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    url = f"https://discord.com/api/v10/guilds/{SUPPORT_SERVER_ID}/members/{user.id}"
                    headers = {
                        "Authorization": f"Bot {bot_token}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "access_token": access_token
                    }
                    await session.put(url, headers=headers, json=payload)

            # Send them to the dashboard after adding to the support server
            return redirect(url_for("dashboard_overview"))
        else:
            # Standard dashboard login
            return redirect(url_for("dashboard_overview"))
    except Exception as e:
        return f"Error logging in: {e}", 400

@app.route("/logout", strict_slashes=False)
async def logout():
    if discord_auth:
        discord_auth.revoke()
    return redirect("/")

@app.errorhandler(Unauthorized)
async def redirect_unauthorized(e):
    return redirect(url_for("login"))



@app.route("/github-webhook", methods=["POST"])
async def github_webhook():
    event = request.headers.get("X-GitHub-Event")
    if event != "push":
        return "Ignored", 200

    payload = await request.get_json()
    if not payload:
        return "Invalid payload", 400

    commits = payload.get("commits", [])
    if not commits:
        return "No commits", 200

    branch = payload.get("ref", "").split("/")[-1]
    repo_name = payload.get("repository", {}).get("full_name", "Unknown Repo")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id FROM changelog_config WHERE id = 1")
    row = cursor.fetchone()

    if not row or not hasattr(app, "bot") or not app.bot.is_ready():
        return "Bot not ready or channel not configured", 200

    channel_id = row[0]
    channel = app.bot.get_channel(channel_id)
    if not channel:
        return "Channel not found", 200

    for commit in commits:
        author_name = commit.get("author", {}).get("name", "Unknown")
        message = commit.get("message", "No commit message")
        commit_url = commit.get("url", "")
        commit_id = commit.get("id", "Unknown")[:7]

        content = f"**Branch:** `{branch}`\n"
        content += f"**Author:** `{author_name}`\n"
        content += f"**Commit:** [`{commit_id}`]({commit_url})\n\n"
        content += f"```\n{message}\n```"

        from cogs import embed_factory
        embed = embed_factory.create_clean_embed(f"🛠️ New Commit to {repo_name}", content)

        app.bot.loop.create_task(channel.send(embed=embed))

    return "OK", 200

# Dashboard Routes

@app.route("/dashboard")
@app.route("/dashboard/")
@requires_authorization
async def dashboard_overview():
    if not await is_authorized():
        return "Unauthorized: You must be an Administrator in a server with the bot.", 403

    user = await discord_auth.fetch_user()

    server_count = len(app.bot.guilds) if hasattr(app, 'bot') and app.bot.is_ready() else 0
    total_users = sum([g.member_count for g in app.bot.guilds if g.member_count]) if hasattr(app, 'bot') and app.bot.is_ready() else 0

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM warnings")
    punishments = cursor.fetchone()[0]

    stats = {
        "server_count": server_count,
        "total_users": total_users,
        "messages_logged": punishments * 42
    }
    return await render_template('dashboard.html', tab='overview', user=user, stats=stats)


@app.route("/dashboard/automod", methods=["GET", "POST"])
@requires_authorization
async def dashboard_automod():
    if not await is_authorized():
        return "Unauthorized", 403

    user = await discord_auth.fetch_user()
    conn = get_db()
    cursor = conn.cursor()
    keys = ['automod_spam', 'automod_invites', 'automod_english', 'automod_bot']

    if request.method == "POST":
        form = await request.form
        for k in keys:
            if k in form:
                cursor.execute("INSERT OR REPLACE INTO server_config (key, value) VALUES (?, ?)", (k, form[k]))
        conn.commit()
        return redirect(url_for("dashboard_automod"))

    cursor.execute("SELECT * FROM server_config WHERE key IN ({})".format(','.join(['?']*len(keys))), keys)
    rows = cursor.fetchall()
    config = {k: "1" for k in keys}
    for r in rows:
        config[r['key']] = r['value']

    return await render_template('dashboard.html', tab='automod', user=user, config=config)


@app.route("/dashboard/leveling")
@requires_authorization
async def dashboard_leveling():
    if not await is_authorized():
        return "Unauthorized", 403

    user = await discord_auth.fetch_user()
    conn = get_db()
    cursor = conn.cursor()

    keys = [
        'xp_min', 'xp_max', 'xp_cooldown', 'leveling_whitelist', 'leveling_blacklist',
        'leveling_role_blacklist', 'leveling_min_length', 'leveling_announcement_channel',
        'leveling_custom_message', 'leveling_role_stacking'
    ]
    cursor.execute(f"SELECT * FROM server_config WHERE key IN ({','.join(['?']*len(keys))})", keys)
    rows = cursor.fetchall()

    # Defaults
    config = {
        "xp_min": 15, "xp_max": 25, "xp_cooldown": 60, "leveling_whitelist": "", "leveling_blacklist": "",
        "leveling_role_blacklist": "", "leveling_min_length": 5, "leveling_announcement_channel": "current",
        "leveling_custom_message": "🎉 **{user}** just leveled up to **Level {level}**!", "leveling_role_stacking": "stack"
    }

    for r in rows:
        if r['key'] in ['xp_min', 'xp_max', 'xp_cooldown', 'leveling_min_length']:
            config[r['key']] = int(r['value'])
        else:
            config[r['key']] = str(r['value'])

    cursor.execute("SELECT level, role_id FROM leveling_rewards ORDER BY level ASC")
    rewards = cursor.fetchall()

    cursor.execute("SELECT role_id, multiplier FROM leveling_multipliers")
    multipliers = cursor.fetchall()

    # Fetch roles and channels from the bot
    roles = []
    channels = []
    if hasattr(app, 'bot') and app.bot.is_ready() and app.bot.guilds:
        guild = app.bot.guilds[0] # Assuming single-server project "Project Nexus"
        roles = [{"id": str(r.id), "name": r.name} for r in guild.roles if not r.is_default()]
        channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels + guild.voice_channels]

    # Helper function to check if an id is in a comma separated string
    def is_selected(id_str, csv_str):
        return id_str in [x.strip() for x in csv_str.split(',') if x.strip()]

    return await render_template('dashboard.html', tab='leveling', user=user, config=config,
                                 rewards=rewards, multipliers=multipliers,
                                 roles=roles, channels=channels, is_selected=is_selected)


@app.route("/dashboard/leveling_settings", methods=["POST"])
@requires_authorization
async def dashboard_leveling_settings():
    if not await is_authorized():
        return "Unauthorized", 403

    form = await request.form
    conn = get_db()
    cursor = conn.cursor()

    # Handle standard inputs
    standard_keys = ['xp_min', 'xp_max', 'xp_cooldown', 'leveling_min_length', 'leveling_announcement_channel', 'leveling_custom_message', 'leveling_role_stacking']
    for k in standard_keys:
        if k in form:
            cursor.execute("INSERT OR REPLACE INTO server_config (key, value) VALUES (?, ?)", (k, form[k]))

    # Handle multi-selects (Choices.js)
    multi_keys = ['leveling_whitelist', 'leveling_blacklist', 'leveling_role_blacklist']
    for k in multi_keys:
        values = form.getlist(k)
        # Combine into comma separated string
        csv_value = ",".join(values)
        cursor.execute("INSERT OR REPLACE INTO server_config (key, value) VALUES (?, ?)", (k, csv_value))

    conn.commit()
    return redirect(url_for("dashboard_leveling"))

@app.route("/dashboard/leveling_multiplier_add", methods=["POST"])
@requires_authorization
async def dashboard_leveling_multiplier_add():
    if not await is_authorized():
        return "Unauthorized", 403

    form = await request.form
    role_id = form.get('role_id')
    multiplier = form.get('multiplier')

    if role_id and multiplier:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO leveling_multipliers (role_id, multiplier) VALUES (?, ?)", (str(role_id), float(multiplier)))
        conn.commit()

    return redirect(url_for("dashboard_leveling"))

@app.route("/dashboard/leveling_multiplier_delete", methods=["POST"])
@requires_authorization
async def dashboard_leveling_multiplier_delete():
    if not await is_authorized():
        return "Unauthorized", 403

    form = await request.form
    role_id = form.get('role_id')

    if role_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leveling_multipliers WHERE role_id = ?", (str(role_id),))
        conn.commit()

    return redirect(url_for("dashboard_leveling"))


@app.route("/dashboard/leveling_reward_add", methods=["POST"])
@requires_authorization
async def dashboard_leveling_reward_add():
    if not await is_authorized():
        return "Unauthorized", 403

    form = await request.form
    level = form.get('level')
    role_id = form.get('role_id')

    if level and role_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO leveling_rewards (level, role_id) VALUES (?, ?)", (level, str(role_id)))
        conn.commit()

    return redirect(url_for("dashboard_leveling"))


@app.route("/dashboard/leveling_reward_delete", methods=["POST"])
@requires_authorization
async def dashboard_leveling_reward_delete():
    if not await is_authorized():
        return "Unauthorized", 403

    form = await request.form
    level = form.get('level')

    if level:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leveling_rewards WHERE level = ?", (level,))
        conn.commit()

    return redirect(url_for("dashboard_leveling"))


@app.route('/assets/<path:filename>')
async def custom_static(filename):
    return await send_from_directory('assets', filename)

async def run_server(bot):
    app.bot = bot
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    config = Config()
    config.bind = ["0.0.0.0:12166"]
    print("Starting Quart Web Server on port 12166...")
    await serve(app, config)
