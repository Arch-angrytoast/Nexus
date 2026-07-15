import discord
import sqlite3
import datetime
from . import snark_pool

class DossierView(discord.ui.View):
    def __init__(self, target: discord.Member, db_conn: sqlite3.Connection):
        super().__init__(timeout=600)
        self.target = target
        self.db_conn = db_conn

        # Start on Discord Identity page
        self.current_page = "identity"

    def generate_identity_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="CLASSIFIED DOSSIER",
            description=f"**Target:** {self.target.mention} (`{self.target.id}`)",
            color=discord.Color.dark_theme()
        )
        if self.target.display_avatar:
            embed.set_thumbnail(url=self.target.display_avatar.url)

        # Account Creation & Join
        created_at = f"<t:{int(self.target.created_at.timestamp())}:R>"
        joined_at = f"<t:{int(self.target.joined_at.timestamp())}:R>" if self.target.joined_at else "Unknown"
        embed.add_field(name="🕒 Account Age", value=f"Created: {created_at}\nJoined Server: {joined_at}", inline=False)

        # Status & Devices
        status_map = {
            discord.Status.online: "🟢 Online",
            discord.Status.idle: "🌙 Idle",
            discord.Status.dnd: "⛔ Do Not Disturb",
            discord.Status.offline: "⚫ Offline",
            discord.Status.invisible: "👻 Invisible"
        }
        current_status = status_map.get(self.target.status, str(self.target.status).capitalize())

        devices = []
        if self.target.desktop_status != discord.Status.offline:
            devices.append("🖥️ Desktop")
        if self.target.mobile_status != discord.Status.offline:
            devices.append("📱 Mobile")
        if self.target.web_status != discord.Status.offline:
            devices.append("🌐 Web")

        device_str = " | ".join(devices) if devices else "None detected"
        embed.add_field(name="📡 Presence Status", value=f"**Status:** {current_status}\n**Active Devices:** {device_str}", inline=False)

        # Roles
        roles = [r.mention for r in reversed(self.target.roles) if r != self.target.guild.default_role]
        roles_str = " ".join(roles[:10]) + ("..." if len(roles) > 10 else "")
        embed.add_field(name="🏷️ Key Roles", value=roles_str if roles else "None", inline=False)

        # Activities
        if self.target.activities:
            acts = []
            for act in self.target.activities:
                if isinstance(act, discord.CustomActivity):
                    acts.append(f"Custom: {act.name}")
                elif isinstance(act, discord.Game):
                    acts.append(f"Playing: {act.name}")
                elif isinstance(act, discord.Streaming):
                    acts.append(f"Streaming: {act.name}")
                elif isinstance(act, discord.Spotify):
                    acts.append(f"Listening to Spotify: {act.title}")
            embed.add_field(name="🎮 Current Activities", value="\n".join(acts[:5]), inline=False)

        return embed

    def generate_moderation_embed(self) -> discord.Embed:
        cursor = self.db_conn.cursor()

        # Get total points in last 30 days
        thirty_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat()
        cursor.execute("SELECT SUM(points) FROM warnings WHERE user_id = ? AND timestamp > ?", (self.target.id, thirty_days_ago))
        total_points = cursor.fetchone()[0] or 0

        # Get last 5 warnings
        cursor.execute("SELECT mod_id, reason, points, timestamp FROM warnings WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", (self.target.id,))
        rows = cursor.fetchall()

        embed = discord.Embed(
            title="MODERATION RECORD",
            description=f"**Target:** {self.target.mention}\n**Threat Level (30d):** {total_points}/100 pts",
            color=discord.Color.red()
        )
        if self.target.display_avatar:
            embed.set_thumbnail(url=self.target.display_avatar.url)

        if rows:
            record_lines = []
            for mod_id, reason, points, timestamp in rows:
                dt = datetime.datetime.fromisoformat(timestamp)
                formatted_date = f"<t:{int(dt.timestamp())}:d>"
                record_lines.append(f"• {formatted_date}: **{points} pts** - {reason} (by <@{mod_id}>)")
            embed.add_field(name="Recent Infractions", value="\n".join(record_lines), inline=False)
        else:
            embed.add_field(name="Recent Infractions", value="Clean record.", inline=False)

        return embed

    def generate_nexus_embed(self) -> discord.Embed:
        cursor = self.db_conn.cursor()

        embed = discord.Embed(
            title="NEXUS INTEL",
            description=f"**Target:** {self.target.mention}\nData gathered from Nexus Joke Meters.",
            color=discord.Color.purple()
        )
        if self.target.display_avatar:
            embed.set_thumbnail(url=self.target.display_avatar.url)

        cursor.execute("SELECT meter_name, emoji FROM joke_meters ORDER BY meter_name ASC")
        rows = cursor.fetchall()

        if rows:
            meter_lines = []
            utc_date = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
            for name, emoji in rows:
                score, _, _ = snark_pool.calculate_meter(self.target.id, name, self.db_conn)
                # Check override
                cursor.execute("SELECT score FROM score_overrides WHERE target_id = ? AND meter_name = ? AND utc_date = ?", (self.target.id, name, utc_date))
                override = cursor.fetchone()
                is_overridden = " *(Admin Overridden)*" if override else ""

                meter_lines.append(f"{emoji} **{name.capitalize()}**: {score}%{is_overridden}")

            embed.add_field(name="Current Meter Ratings", value="\n".join(meter_lines[:15]), inline=False)
        else:
            embed.add_field(name="Current Meter Ratings", value="No meters available in database.", inline=False)

        return embed

    async def update_page(self, interaction: discord.Interaction):
        embed = None
        if self.current_page == "identity":
            embed = self.generate_identity_embed()
        elif self.current_page == "mod":
            embed = self.generate_moderation_embed()
        elif self.current_page == "nexus":
            embed = self.generate_nexus_embed()

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Discord Identity", emoji="📘", style=discord.ButtonStyle.primary, row=0)
    async def btn_identity(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "identity"
        await self.update_page(interaction)

    @discord.ui.button(label="Moderation Record", emoji="🚨", style=discord.ButtonStyle.danger, row=0)
    async def btn_mod(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "mod"
        await self.update_page(interaction)

    @discord.ui.button(label="Nexus Stats", emoji="🃏", style=discord.ButtonStyle.success, row=0)
    async def btn_nexus(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "nexus"
        await self.update_page(interaction)
