import os
import sqlite3
import asyncio
from quart import Quart, redirect, url_for, render_template, request, send_from_directory
from quart_discord import DiscordOAuth2Session, requires_authorization, Unauthorized
from dotenv import load_dotenv

load_dotenv()

app = Quart(__name__)
app.secret_key = os.getenv("QUART_SECRET_KEY", os.urandom(24))
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true" # For testing locally

app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
app.config["DISCORD_REDIRECT_URI"] = os.getenv("OAUTH_REDIRECT_URI", "http://78.154.103.22:12166/callback")

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
        # Fallback to bot owner ID
        user = await discord_auth.fetch_user()
        if str(user.id) == os.getenv("OWNER_ID"):
            return True

        user_guilds = await discord_auth.fetch_guilds()
        bot_guild_ids = [g.id for g in app.bot.guilds]
        for g in user_guilds:
            # quart-discord returns a discord.Permissions object for g.permissions
            if g.id in bot_guild_ids and getattr(g.permissions, 'administrator', False):
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

@app.route("/login/")
async def login():
    if not discord_auth:
        return "Discord OAuth not configured", 500
    return await discord_auth.create_session()

@app.route("/callback/")
async def callback():
    if not discord_auth:
        return "Discord OAuth not configured", 500
    try:
        await discord_auth.callback()
        return redirect(url_for("dashboard_overview"))
    except Exception as e:
        return f"Error logging in: {e}", 400

@app.route("/logout/")
async def logout():
    if discord_auth:
        discord_auth.revoke()
    return redirect("/")

@app.errorhandler(Unauthorized)
async def redirect_unauthorized(e):
    return redirect(url_for("login"))


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
