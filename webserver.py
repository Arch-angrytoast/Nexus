import os
import sqlite3
import datetime
from quart import Quart, render_template, request, redirect, url_for, send_from_directory, session, jsonify
import aiohttp
from functools import wraps
import urllib.parse

app = Quart(__name__)

app.secret_key = os.getenv("QUART_SECRET_KEY", os.urandom(32))

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "https://nexuscore.wisp.uno/callback")
SUPPORT_SERVER_ID = os.getenv("SUPPORT_SERVER_ID", "1519633747559841844")
API_BASE_URL = 'https://discord.com/api/v10'

def get_db():
    conn = sqlite3.connect('bot_data.db')
    conn.row_factory = sqlite3.Row
    return conn

def log_audit(guild_id, user_id, user_name, action):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor.execute("INSERT INTO dashboard_audit_logs (guild_id, user_id, user_name, action, timestamp) VALUES (?, ?, ?, ?, ?)",
                   (guild_id, user_id, user_name, action, now))
    conn.commit()

# --- RAW OAUTH2 ---
async def get_access_token(code):
    data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': DISCORD_REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    async with aiohttp.ClientSession() as http_session:
        async with http_session.post(f"{API_BASE_URL}/oauth2/token", data=data, headers=headers) as resp:
            if resp.status != 200:
                return None
            return await resp.json()

async def fetch_user_data(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as http_session:
        async with http_session.get(f"{API_BASE_URL}/users/@me", headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

async def join_support_server(access_token, user_id):
    bot_token = os.getenv("DISCORD_TOKEN")
    if not bot_token: return
    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}
    payload = {"access_token": access_token}
    async with aiohttp.ClientSession() as http_session:
        await http_session.put(f"{API_BASE_URL}/guilds/{SUPPORT_SERVER_ID}/members/{user_id}", headers=headers, json=payload)

# --- MIDDLEWARE ---
def requires_authorization(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return await f(*args, **kwargs)
    return decorated

async def check_guild_auth(guild_id):
    user = session.get("user")
    if not user: return False

    if str(user["id"]) == str(os.getenv("OWNER_ID")):
        return True

    # Natively check guild perms via bot cache if possible
    if hasattr(app, "bot") and app.bot.is_ready():
        bot_guild = app.bot.get_guild(int(guild_id))
        if bot_guild:
            member = bot_guild.get_member(int(user["id"]))
            if member:
                if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
                    return True

                # Check DB roles
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT role_id FROM dashboard_permissions WHERE guild_id = ?", (str(guild_id),))
                allowed_roles = [r[0] for r in cursor.fetchall()]
                member_role_ids = [str(r.id) for r in member.roles]

                for rid in allowed_roles:
                    if rid in member_role_ids:
                        return True

    return False

# --- OAUTH ROUTES ---
@app.route("/")
async def index():
    user = session.get("user")
    return await render_template('landing.html', user=user)

@app.route("/login", strict_slashes=False)
async def login():
    if not DISCORD_CLIENT_ID: return "Missing CLIENT_ID", 500
    encoded_uri = urllib.parse.quote(DISCORD_REDIRECT_URI, safe='')
    url = f"{API_BASE_URL}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={encoded_uri}&response_type=code&scope=identify%20guilds"
    return redirect(url)

@app.route("/invite", strict_slashes=False)
async def invite():
    if not DISCORD_CLIENT_ID: return "Missing CLIENT_ID", 500
    encoded_uri = urllib.parse.quote(DISCORD_REDIRECT_URI, safe='')
    url = f"{API_BASE_URL}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={encoded_uri}&response_type=code&scope=identify%20guilds%20guilds.join"
    return redirect(url)

@app.route("/bot-invite", strict_slashes=False)
async def bot_invite():
    if not DISCORD_CLIENT_ID: return "Missing CLIENT_ID", 500
    encoded_uri = urllib.parse.quote(DISCORD_REDIRECT_URI, safe='')
    url = f"{API_BASE_URL}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&permissions=8&redirect_uri={encoded_uri}&response_type=code&scope=identify%20bot%20guilds%20guilds.join"
    return redirect(url)

@app.route("/callback", strict_slashes=False)
async def callback():
    code = request.args.get("code")
    if not code: return "No authorization code provided.", 400

    token_data = await get_access_token(code)
    if not token_data: return "Failed to fetch access token.", 400

    access_token = token_data.get("access_token")
    scopes = token_data.get("scope", "").split()

    user_data = await fetch_user_data(access_token)
    if not user_data: return "Failed to fetch user data.", 400

    session.permanent = True
    session["user"] = {
        "id": user_data["id"],
        "name": user_data.get("global_name") or user_data["username"],
        "avatar": user_data.get("avatar"),
        "access_token": access_token
    }

    if "guilds.join" in scopes:
        await join_support_server(access_token, user_data["id"])

    return redirect(url_for("dashboard_selector"))

@app.route("/logout", strict_slashes=False)
async def logout():
    session.clear()
    return redirect("/")

# --- DASHBOARD ---
@app.route("/dashboard", strict_slashes=False)
@requires_authorization
async def dashboard_selector():
    user = session["user"]

    # Fetch guilds from api
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    async with aiohttp.ClientSession() as http_session:
        async with http_session.get(f"{API_BASE_URL}/users/@me/guilds", headers=headers) as resp:
            if resp.status == 200:
                guilds = await resp.json()
            else:
                guilds = []

    owner_id = os.getenv("OWNER_ID")
    is_owner = str(user["id"]) == str(owner_id)

    bot_guild_ids = []
    if hasattr(app, "bot") and app.bot.is_ready():
        bot_guild_ids = [str(g.id) for g in app.bot.guilds]

    display_guilds = []
    for g in guilds:
        perms = int(g.get('permissions', 0))
        has_manage = (perms & 0x8) or (perms & 0x20)

        if has_manage or is_owner:
            icon = f"https://cdn.discordapp.com/icons/{g['id']}/{g['icon']}.png" if g.get('icon') else "https://cdn.discordapp.com/embed/avatars/0.png"
            display_guilds.append({
                "id": str(g["id"]),
                "name": g["name"],
                "icon_url": icon,
                "has_bot": str(g["id"]) in bot_guild_ids
            })

    return await render_template('server_selector.html', user=user, guilds=display_guilds)

@app.route("/dashboard/<guild_id>/", strict_slashes=False)
@requires_authorization
async def dashboard_core(guild_id):
    if not await check_guild_auth(guild_id): return "Unauthorized", 403
    user = session["user"]
    guild = app.bot.get_guild(int(guild_id)) if hasattr(app, "bot") else None
    guild_name = guild.name if guild else "Unknown Server"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM server_config WHERE guild_id = ?", (guild_id,))
    config = {r['key']: r['value'] for r in cursor.fetchall()}
    return await render_template('dashboard_layout.html', user=user, guild_id=guild_id, guild_name=guild_name, tab='core', config=config)

@app.route("/dashboard/<guild_id>/modules", strict_slashes=False)
@requires_authorization
async def dashboard_modules(guild_id):
    if not await check_guild_auth(guild_id): return "Unauthorized", 403
    user = session["user"]
    guild = app.bot.get_guild(int(guild_id)) if hasattr(app, "bot") else None
    guild_name = guild.name if guild else "Unknown Server"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM server_config WHERE guild_id = ?", (guild_id,))
    config = {r['key']: r['value'] for r in cursor.fetchall()}

    cursor.execute("SELECT level, role_id FROM leveling_rewards WHERE guild_id = ? ORDER BY level ASC", (guild_id,))
    rewards = cursor.fetchall()

    cursor.execute("SELECT role_id, multiplier FROM leveling_multipliers WHERE guild_id = ?", (guild_id,))
    multipliers = cursor.fetchall()

    roles, channels = [], []
    if guild:
        roles = [{"id": str(r.id), "name": r.name} for r in guild.roles if not r.is_default()]
        channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels + guild.voice_channels]

    def is_selected(id_str, csv_str):
        if not csv_str: return False
        return id_str in [x.strip() for x in str(csv_str).split(',') if x.strip()]

    return await render_template('dashboard_layout.html', user=user, guild_id=guild_id, guild_name=guild_name, tab='modules', config=config, rewards=rewards, multipliers=multipliers, roles=roles, channels=channels, is_selected=is_selected)

@app.route("/dashboard/<guild_id>/management", strict_slashes=False)
@requires_authorization
async def dashboard_management(guild_id):
    if not await check_guild_auth(guild_id): return "Unauthorized", 403
    user = session["user"]
    guild = app.bot.get_guild(int(guild_id)) if hasattr(app, "bot") else None
    guild_name = guild.name if guild else "Unknown Server"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT role_id FROM dashboard_permissions WHERE guild_id = ?", (guild_id,))
    perm_roles = cursor.fetchall()

    cursor.execute("SELECT user_name, action, timestamp FROM dashboard_audit_logs WHERE guild_id = ? ORDER BY id DESC LIMIT 50", (guild_id,))
    logs = cursor.fetchall()

    roles = []
    if guild:
        roles = [{"id": str(r.id), "name": r.name, "color": str(r.color)} for r in guild.roles if not r.is_default()]

    return await render_template('dashboard_layout.html', user=user, guild_id=guild_id, guild_name=guild_name, tab='management', perm_roles=perm_roles, logs=logs, roles=roles)

# --- API ---
@app.route("/api/dashboard/<guild_id>/save", methods=["POST"])
@requires_authorization
async def api_save_config(guild_id):
    if not await check_guild_auth(guild_id): return jsonify({"error": "Unauthorized"}), 403
    user = session["user"]
    data = await request.get_json()
    if not data: return jsonify({"error": "No data"}), 400

    conn = get_db()
    cursor = conn.cursor()
    changes = []
    for key, value in data.items():
        cursor.execute("INSERT OR REPLACE INTO server_config (guild_id, key, value) VALUES (?, ?, ?)", (guild_id, key, str(value)))
        changes.append(key)

    conn.commit()
    if changes: log_audit(guild_id, str(user["id"]), user["name"], f"Updated config: {', '.join(changes)}")
    return jsonify({"success": True})

@app.route("/api/dashboard/<guild_id>/permissions", methods=["POST", "DELETE"])
@requires_authorization
async def api_permissions(guild_id):
    if not await check_guild_auth(guild_id): return jsonify({"error": "Unauthorized"}), 403
    user = session["user"]
    data = await request.get_json()
    role_id = data.get("role_id")
    if not role_id: return jsonify({"error": "Missing role_id"}), 400

    conn = get_db()
    cursor = conn.cursor()
    if request.method == "POST":
        cursor.execute("INSERT OR REPLACE INTO dashboard_permissions (guild_id, role_id) VALUES (?, ?)", (guild_id, role_id))
        log_audit(guild_id, str(user["id"]), user["name"], f"Granted access to Role: {role_id}")
    else:
        cursor.execute("DELETE FROM dashboard_permissions WHERE guild_id = ? AND role_id = ?", (guild_id, role_id))
        log_audit(guild_id, str(user["id"]), user["name"], f"Revoked access from Role: {role_id}")

    conn.commit()
    return jsonify({"success": True})

@app.route("/dashboard/<guild_id>/leveling_reward_add", methods=["POST"])
@requires_authorization
async def dashboard_leveling_reward_add(guild_id):
    if not await check_guild_auth(guild_id): return "Unauthorized", 403
    form = await request.form
    level, role_id = form.get('level'), form.get('role_id')
    if level and role_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO leveling_rewards (guild_id, level, role_id) VALUES (?, ?, ?)", (guild_id, level, str(role_id)))
        conn.commit()
    return redirect(url_for("dashboard_modules", guild_id=guild_id))

@app.route("/dashboard/<guild_id>/leveling_reward_delete", methods=["POST"])
@requires_authorization
async def dashboard_leveling_reward_delete(guild_id):
    if not await check_guild_auth(guild_id): return "Unauthorized", 403
    form = await request.form
    level = form.get('level')
    if level:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leveling_rewards WHERE guild_id = ? AND level = ?", (guild_id, level))
        conn.commit()
    return redirect(url_for("dashboard_modules", guild_id=guild_id))

@app.route("/dashboard/<guild_id>/leveling_multiplier_add", methods=["POST"])
@requires_authorization
async def dashboard_leveling_multiplier_add(guild_id):
    if not await check_guild_auth(guild_id): return "Unauthorized", 403
    form = await request.form
    role_id, multiplier = form.get('role_id'), form.get('multiplier')
    if role_id and multiplier:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO leveling_multipliers (guild_id, role_id, multiplier) VALUES (?, ?, ?)", (guild_id, str(role_id), float(multiplier)))
        conn.commit()
    return redirect(url_for("dashboard_modules", guild_id=guild_id))

@app.route("/dashboard/<guild_id>/leveling_multiplier_delete", methods=["POST"])
@requires_authorization
async def dashboard_leveling_multiplier_delete(guild_id):
    if not await check_guild_auth(guild_id): return "Unauthorized", 403
    form = await request.form
    role_id = form.get('role_id')
    if role_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leveling_multipliers WHERE guild_id = ? AND role_id = ?", (guild_id, str(role_id)))
        conn.commit()
    return redirect(url_for("dashboard_modules", guild_id=guild_id))

# --- WEBHOOK ---
@app.route("/github-webhook", methods=["POST"])
async def github_webhook():
    event = request.headers.get("X-GitHub-Event")
    if event != "push": return "Ignored", 200

    payload = await request.get_json()
    if not payload: return "Invalid payload", 400

    commits = payload.get("commits", [])
    if not commits: return "No commits", 200

    branch = payload.get("ref", "").split("/")[-1]
    repo_name = payload.get("repository", {}).get("full_name", "Unknown Repo")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id FROM changelog_config WHERE id = 1")
    row = cursor.fetchone()

    if not row or not hasattr(app, "bot") or not app.bot.is_ready(): return "Bot not ready or channel not configured", 200

    channel_id = row[0]
    channel = app.bot.get_channel(channel_id)
    if not channel: return "Channel not found", 200

    for commit in commits:
        author_name = commit.get("author", {}).get("name", "Unknown")
        message = commit.get("message", "No commit message")
        commit_url = commit.get("url", "")
        commit_id = commit.get("id", "Unknown")[:7]

        content = f"**Branch:** `{branch}`\n**Author:** `{author_name}`\n**Commit:** [`{commit_id}`]({commit_url})\n\n```\n{message}\n```"
        from cogs import embed_factory
        embed = embed_factory.create_clean_embed(f"🛠️ New Commit to {repo_name}", content)
        app.bot.loop.create_task(channel.send(embed=embed))

    return "OK", 200


@app.route('/api/preview_url', methods=['GET'])
async def preview_url():
    url = request.args.get('url')
    if not url: return jsonify({"error": "No url"}), 400

    # In a real app we'd fetch OpenGraph meta tags, but here we can just do a very basic validation/return
    # This is a stub to make the JS embed work nicely if requested
    return jsonify({"url": url})

@app.route('/assets/<path:filename>')
async def custom_static(filename):
    return await send_from_directory('assets', filename)

@app.route("/dashboard/<guild_id>/audit-logs", methods=["GET", "POST"], strict_slashes=False)
async def dashboard_audit_logs_config(guild_id):
    if not await check_guild_auth(guild_id): return "Unauthorized", 403
    guild = bot.get_guild(int(guild_id))
    if not guild: return "Guild not found", 404
    user = await get_current_user()
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        form = await request.form
        msg_ch = form.get("message_channel") or None
        mem_ch = form.get("member_channel") or None
        srv_ch = form.get("server_channel") or None
        voc_ch = form.get("voice_channel") or None

        # Ensure config exists
        cursor.execute("SELECT 1 FROM audit_log_config WHERE guild_id = ?", (str(guild_id),))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO audit_log_config (guild_id) VALUES (?)", (str(guild_id),))

        cursor.execute('''
            UPDATE audit_log_config
            SET message_channel = ?, member_channel = ?, server_channel = ?, voice_channel = ?
            WHERE guild_id = ?
        ''', (msg_ch, mem_ch, srv_ch, voc_ch, str(guild_id)))
        conn.commit()
        return redirect(url_for("dashboard_audit_logs_config", guild_id=guild_id))

    cursor.execute("SELECT message_channel, member_channel, server_channel, voice_channel FROM audit_log_config WHERE guild_id = ?", (str(guild_id),))
    row = cursor.fetchone()

    # Dictionary of channels grouped by category for the dropdowns
    text_channels = {}
    for ch in guild.text_channels:
        cat_name = ch.category.name if ch.category else "Uncategorized"
        if cat_name not in text_channels: text_channels[cat_name] = []
        text_channels[cat_name].append(ch)

    config = {
        "message_channel": row[0] if row else None,
        "member_channel": row[1] if row else None,
        "server_channel": row[2] if row else None,
        "voice_channel": row[3] if row else None
    }

    return await render_template(
        "audit_logs.html",
        guild=guild,
        user=user,
        text_channels=text_channels,
        audit_config=config
    )

async def run_server(bot):
    app.bot = bot
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    config = Config()
    config.bind = ["0.0.0.0:12166"]
    print("Starting Quart Web Server on port 12166...")
    await serve(app, config)
