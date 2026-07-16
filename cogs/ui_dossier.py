import discord
import sqlite3
import datetime
from . import snark_pool
from . import embed_factory

class DossierView(discord.ui.View):
    def __init__(self, target: discord.Member, db_conn: sqlite3.Connection):
        super().__init__(timeout=600)
        self.target = target
        self.db_conn = db_conn
        self.current_page = "identity"

    def generate_identity_embed(self) -> discord.Embed:
        created_at = f"<t:{int(self.target.created_at.timestamp())}:R>"
        joined_at = f"<t:{int(self.target.joined_at.timestamp())}:R>" if self.target.joined_at else "Unknown"

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

        roles = [r.mention for r in reversed(self.target.roles) if r != self.target.guild.default_role]
        roles_str = " ".join(roles[:10]) + ("..." if len(roles) > 10 else "")


        acts = []
        if self.target.activities:
            for act in self.target.activities:
                if isinstance(act, discord.CustomActivity):
                    acts.append(f"Custom: {act.name}")
                elif isinstance(act, discord.Game):
                    acts.append(f"Playing: {act.name}")
                elif isinstance(act, discord.Streaming):
                    acts.append(f"Streaming: {act.name}")
                elif isinstance(act, discord.Spotify):
                    acts.append(f"Listening to Spotify: {act.title}")
        acts_str = "\n".join(acts[:5]) if acts else "None"

        content = f"**Target:** {self.target.mention} (`{self.target.id}`)\n\n"
        content += f"**🕒 Account Age**\nCreated: {created_at}\nJoined Server: {joined_at}\n\n"
        content += f"**📡 Presence Status**\nStatus: {current_status}\nActive Devices: {device_str}\n\n"
        content += f"**🏷️ Key Roles**\n{roles_str}\n\n"
        content += f"**🎮 Current Activities**\n{acts_str}"

        return embed_factory.create_clean_embed("CLASSIFIED DOSSIER - Identity", content, thumbnail_url=self.target.display_avatar.url if self.target.display_avatar else None)

    def generate_moderation_embed(self) -> discord.Embed:
        cursor = self.db_conn.cursor()

        thirty_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat()
        cursor.execute("SELECT SUM(points) FROM warnings WHERE user_id = ? AND timestamp > ?", (self.target.id, thirty_days_ago))
        total_points = cursor.fetchone()[0] or 0

        cursor.execute("SELECT mod_id, reason, points, timestamp FROM warnings WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", (self.target.id,))
        rows = cursor.fetchall()

        content = f"**Target:** {self.target.mention}\n**Threat Level (30d):** {total_points}/100 pts\n\n"
        content += "**Recent Infractions:**\n"

        if rows:
            for mod_id, reason, points, timestamp in rows:
                dt = datetime.datetime.fromisoformat(timestamp)
                formatted_date = f"<t:{int(dt.timestamp())}:d>"
                content += f"• {formatted_date}: **{points} pts** - {reason} (by <@{mod_id}>)\n"
        else:
            content += "Clean record."

        return embed_factory.create_clean_embed("CLASSIFIED DOSSIER - Moderation", content, thumbnail_url=self.target.display_avatar.url if self.target.display_avatar else None, color=discord.Color.brand_red())

    def generate_nexus_embed(self) -> discord.Embed:
        cursor = self.db_conn.cursor()

        content = f"**Target:** {self.target.mention}\nData gathered from Nexus Joke Meters.\n\n"

        cursor.execute("SELECT meter_name, emoji FROM joke_meters ORDER BY meter_name ASC")
        rows = cursor.fetchall()

        if rows:
            utc_date = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
            for name, emoji in rows[:15]:
                score, _, _ = snark_pool.calculate_meter(self.target.id, name, self.db_conn)
                cursor.execute("SELECT score FROM score_overrides WHERE target_id = ? AND meter_name = ? AND utc_date = ?", (self.target.id, name, utc_date))
                override = cursor.fetchone()
                is_overridden = " *(Admin Overridden)*" if override else ""

                content += f"{emoji} **{name.capitalize()}**: {score}%{is_overridden}\n"
        else:
            content += "No meters available in database."

        return embed_factory.create_clean_embed("CLASSIFIED DOSSIER - Nexus Intel", content, thumbnail_url=self.target.display_avatar.url if self.target.display_avatar else None, color=discord.Color.purple())

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
