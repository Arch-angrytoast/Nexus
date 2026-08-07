import os
import sqlite3
import datetime
from quart import Quart, render_template, request, redirect, url_for, send_from_directory, jsonify
from quart_discord import DiscordOAuth2Session, requires_authorization, Unauthorized
from functools import wraps

app = Quart(__name__)

app.secret_key = os.getenv("QUART_SECRET_KEY", os.urandom(32))
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true" # For testing locally

app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
app.config["DISCORD_REDIRECT_URI"] = os.getenv("OAUTH_REDIRECT_URI", "http://78.154.103.22:12166/callback")

SUPPORT_SERVER_ID = os.getenv("SUPPORT_SERVER_ID", "1519633747559841844")

# Only initialize discord auth if client ID is set
if app.config["DISCORD_CLIENT_ID"]:
    discord_auth = DiscordOAuth2Session(app)
else:
    discord_auth = None

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

async def check_guild_auth(guild_id):
    if not discord_auth:
        return False

    user = await discord_auth.fetch_user()

    # 1. Bot Owner bypass
    owner_id = os.getenv("OWNER_ID")
    if str(user.id) == str(owner_id):
        return True

    # 2. Check if user is in the guild and has Manage Server/Admin natively
    guilds = await discord_auth.fetch_guilds()
    target_guild = next((g for g in guilds if str(g.id) == str(guild_id)), None)

    if target_guild:
        perms = getattr(target_guild, 'permissions', None)
        if perms and (perms.administrator or perms.manage_guild):
            return True

    # 3. Check Delegated Roles
    # To check roles, we need the bot's cache since OAuth guilds don't return member roles by default,
    # or we make an API call. For speed, we will use the bot's cache if the bot is in the server.
    if hasattr(app, "bot") and app.bot.is_ready():
        bot_guild = app.bot.get_guild(int(guild_id))
        if bot_guild:
            member = bot_guild.get_member(user.id)
            if member:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT role_id FROM dashboard_permissions WHERE guild_id = ?", (str(guild_id),))
                allowed_roles = [r[0] for r in cursor.fetchall()]
                member_role_ids = [str(r.id) for r in member.roles]

                # If they have ANY allowed role, let them in
                for rid in allowed_roles:
                    if rid in member_role_ids:
                        return True

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
            return redirect(url_for("dashboard_selector"))
        else:
            # Standard dashboard login
            return redirect(url_for("dashboard_selector"))
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


# --- WEBHOOK ---
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


# --- NEW DASHBOARD ARCHITECTURE ---

@app.route("/dashboard", strict_slashes=False)
@requires_authorization
async def dashboard_selector():
    user = await discord_auth.fetch_user()
    guilds = await discord_auth.fetch_guilds()

    owner_id = os.getenv("OWNER_ID")
    is_owner = str(user.id) == str(owner_id)

    bot_guild_ids = []
    if hasattr(app, "bot") and app.bot.is_ready():
        bot_guild_ids = [str(g.id) for g in app.bot.guilds]

    display_guilds = []
    for g in guilds:
        perms = getattr(g, 'permissions', None)
        has_manage = perms and (perms.administrator or perms.manage_guild)

        # In a real app we'd also check database delegated permissions here for servers they don't own,
        # but that requires API spam. So we only show servers they natively manage, OR the owner bypass.
        if has_manage or is_owner:
            display_guilds.append({
                "id": str(g.id),
                "name": g.name,
                "icon_url": g.icon_url or "https://cdn.discordapp.com/embed/avatars/0.png",
                "has_bot": str(g.id) in bot_guild_ids
            })

    return await render_template('server_selector.html', user=user, guilds=display_guilds)

@app.route("/dashboard/<guild_id>/", strict_slashes=False)
@requires_authorization
async def dashboard_core(guild_id):
    if not await check_guild_auth(guild_id):
        return "Unauthorized: You do not have permission to manage this server.", 403

    user = await discord_auth.fetch_user()
    guild = app.bot.get_guild(int(guild_id)) if hasattr(app, "bot") else None
    guild_name = guild.name if guild else "Unknown Server"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM server_config WHERE guild_id = ?", (guild_id,))
    rows = cursor.fetchall()
    config = {r['key']: r['value'] for r in rows}

    return await render_template('dashboard_layout.html',
                                 user=user,
                                 guild_id=guild_id,
                                 guild_name=guild_name,
                                 tab='core',
                                 config=config)

@app.route("/dashboard/<guild_id>/modules", strict_slashes=False)
@requires_authorization
async def dashboard_modules(guild_id):
    if not await check_guild_auth(guild_id):
        return "Unauthorized", 403

    user = await discord_auth.fetch_user()
    guild = app.bot.get_guild(int(guild_id)) if hasattr(app, "bot") else None
    guild_name = guild.name if guild else "Unknown Server"

    conn = get_db()
    cursor = conn.cursor()

    # Get Config
    cursor.execute("SELECT key, value FROM server_config WHERE guild_id = ?", (guild_id,))
    rows = cursor.fetchall()
    config = {r['key']: r['value'] for r in rows}

    # Leveling specific data
    cursor.execute("SELECT level, role_id FROM leveling_rewards WHERE guild_id = ? ORDER BY level ASC", (guild_id,))
    rewards = cursor.fetchall()

    cursor.execute("SELECT role_id, multiplier FROM leveling_multipliers WHERE guild_id = ?", (guild_id,))
    multipliers = cursor.fetchall()

    roles = []
    channels = []
    if guild:
        roles = [{"id": str(r.id), "name": r.name} for r in guild.roles if not r.is_default()]
        channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels + guild.voice_channels]

    def is_selected(id_str, csv_str):
        if not csv_str: return False
        return id_str in [x.strip() for x in str(csv_str).split(',') if x.strip()]

    return await render_template('dashboard_layout.html',
                                 user=user,
                                 guild_id=guild_id,
                                 guild_name=guild_name,
                                 tab='modules',
                                 config=config,
                                 rewards=rewards,
                                 multipliers=multipliers,
                                 roles=roles,
                                 channels=channels,
                                 is_selected=is_selected)

@app.route("/dashboard/<guild_id>/management", strict_slashes=False)
@requires_authorization
async def dashboard_management(guild_id):
    if not await check_guild_auth(guild_id):
        return "Unauthorized", 403

    user = await discord_auth.fetch_user()
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

    return await render_template('dashboard_layout.html',
                                 user=user,
                                 guild_id=guild_id,
                                 guild_name=guild_name,
                                 tab='management',
                                 perm_roles=perm_roles,
                                 logs=logs,
                                 roles=roles)

# --- API ENDPOINTS FOR VANILLA JS ---

@app.route("/api/dashboard/<guild_id>/save", methods=["POST"])
@requires_authorization
async def api_save_config(guild_id):
    if not await check_guild_auth(guild_id):
        return jsonify({"error": "Unauthorized"}), 403

    user = await discord_auth.fetch_user()
    data = await request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    conn = get_db()
    cursor = conn.cursor()

    changes = []
    for key, value in data.items():
        cursor.execute("INSERT OR REPLACE INTO server_config (guild_id, key, value) VALUES (?, ?, ?)", (guild_id, key, str(value)))
        changes.append(key)

    conn.commit()

    if changes:
        log_audit(guild_id, str(user.id), user.name, f"Updated configuration: {', '.join(changes)}")

    return jsonify({"success": True})

@app.route("/api/dashboard/<guild_id>/permissions", methods=["POST", "DELETE"])
@requires_authorization
async def api_permissions(guild_id):
    if not await check_guild_auth(guild_id):
        return jsonify({"error": "Unauthorized"}), 403

    user = await discord_auth.fetch_user()
    data = await request.get_json()
    role_id = data.get("role_id")
    if not role_id:
        return jsonify({"error": "Missing role_id"}), 400

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("INSERT OR REPLACE INTO dashboard_permissions (guild_id, role_id) VALUES (?, ?)", (guild_id, role_id))
        log_audit(guild_id, str(user.id), user.name, f"Granted dashboard access to Role ID: {role_id}")
    else:
        cursor.execute("DELETE FROM dashboard_permissions WHERE guild_id = ? AND role_id = ?", (guild_id, role_id))
        log_audit(guild_id, str(user.id), user.name, f"Revoked dashboard access from Role ID: {role_id}")

    conn.commit()
    return jsonify({"success": True})



@app.route("/dashboard/<guild_id>/leveling_reward_add", methods=["POST"])
@requires_authorization
async def dashboard_leveling_reward_add(guild_id):
    if not await check_guild_auth(guild_id):
        return "Unauthorized", 403

    form = await request.form
    level = form.get('level')
    role_id = form.get('role_id')

    if level and role_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO leveling_rewards (guild_id, level, role_id) VALUES (?, ?, ?)", (guild_id, level, str(role_id)))
        conn.commit()

    return redirect(url_for("dashboard_modules", guild_id=guild_id))


@app.route("/dashboard/<guild_id>/leveling_reward_delete", methods=["POST"])
@requires_authorization
async def dashboard_leveling_reward_delete(guild_id):
    if not await check_guild_auth(guild_id):
        return "Unauthorized", 403

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
    if not await check_guild_auth(guild_id):
        return "Unauthorized", 403

    form = await request.form
    role_id = form.get('role_id')
    multiplier = form.get('multiplier')

    if role_id and multiplier:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO leveling_multipliers (guild_id, role_id, multiplier) VALUES (?, ?, ?)", (guild_id, str(role_id), float(multiplier)))
        conn.commit()

    return redirect(url_for("dashboard_modules", guild_id=guild_id))

@app.route("/dashboard/<guild_id>/leveling_multiplier_delete", methods=["POST"])
@requires_authorization
async def dashboard_leveling_multiplier_delete(guild_id):
    if not await check_guild_auth(guild_id):
        return "Unauthorized", 403

    form = await request.form
    role_id = form.get('role_id')

    if role_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leveling_multipliers WHERE guild_id = ? AND role_id = ?", (guild_id, str(role_id)))
        conn.commit()

    return redirect(url_for("dashboard_modules", guild_id=guild_id))

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
