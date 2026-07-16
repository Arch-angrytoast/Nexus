# Nexus: Advanced Discord Bot & Joke Meters

A highly customizable Discord bot (Nexus) built with `discord.py` and `sqlite3` featuring robust moderation, anti-nuke tools, a highly customizable advanced ticket system, comprehensive utility/misc commands, and dynamic "Joke Meters."

## Features

- **Dynamic Joke Meters:** Measures users with daily, deterministic scoring, providing fun progress bars and snarky commentary based on the results. Seed is built from their User ID, meter name, and UTC date.
- **Roleplay Actions:** Kiss, hug, slap, or pat other users with random Giphy-powered GIFs via Slash commands.
- **Advanced Ticket System:** Highly customizable ticket UI builder! Admins can use `/ticket-setup` to create and publish multi-button ticket panels. Each button can be customized with its own label, emoji, specific ping role, and target category. `/ticket-config` handles global fallbacks.
- **Moderation & Automod:** Warning systems, timeout, kick, ban, purge, and an AI-less basic Automod (banned words, anti-spam, invite blocking).
- **Anti-Nuke Systems:** Protects your server against mass bans, kicks, channel deletions, and role tampering.
- **Comprehensive Utilities:** Over 20 hybrid utility commands (e.g., `!avatar`, `!coinflip`, `!serverinfo`, `!math`, `!poll`) plus owner-exclusive system diagnostics (`/status`, `/uptime`, `/diagnostics`, `/server-insights`).
- **Universal Invisible UI:** All embeds are formatted with Discord's `#2B2D31` background hex using `embed_factory.py`, removing the colored left border for a clean, seamless integration into Discord's dark mode.
- **Hybrid Command System:** Almost all commands support both standard prefixes (e.g., `!ban`) and Discord slash commands (e.g., `/ban`). Joke Actions and Joke Meters deliberately remain slash-only/prefix-hybrid as requested.

## Prerequisites

- Python 3.10+
- A Discord Bot Token (created from the [Discord Developer Portal](https://discord.com/developers/applications)).
- Nexus must have **Message Content**, **Server Members**, and **Presence** Intents enabled in the Developer Portal.

## Setup

1. **Clone the repository.**
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure Environment:**
   Copy `.env.example` to `.env` in the root directory and configure it:
   ```env
   DISCORD_TOKEN=your_discord_bot_token_here
   COMMAND_PREFIX=!
   GIPHY_API_KEY=your_giphy_api_key_here
   OWNER_ID=your_discord_user_id_here
   ```
4. **Run Nexus:**
   ```bash
   python bot.py
   ```

Upon running for the first time, Nexus will automatically generate `bot_data.db` and initialize the required tables.

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0) - see the [LICENSE](LICENSE) file for details.
