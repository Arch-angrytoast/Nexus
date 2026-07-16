# Nexus: The Discord Joke Meter

A highly customizable Discord bot (Nexus) built with `discord.py` and `sqlite3` that features dynamic "Joke Meters." It measures users with daily, deterministic scoring, providing fun progress bars and snarky commentary based on the results.

## Features

- **Daily Deterministic Scores:** Users receive the same score for a specific meter for 24 hours. The seed is built from their User ID, the meter name, and the current UTC date.
- **Snark Pool:** Scores are categorized into 4 tiers, pulling random, snarky responses formatted into an invisible-UI embed.
- **Hybrid Command System:**
  - **Prefix Listener:** Users can type commands like `!sigma @User` or reply to a message with `!sigma`.
  - **Slash Command:** A `/measure [meter] [user]` command for easy use in bot channels.
- **Admin Management:** Discord Administrators can use `/add-meter` and `/remove-meter` to dynamically update the bot's database on the fly.

## Prerequisites

- Python 3.10+
- A Discord Bot Token (created from the [Discord Developer Portal](https://discord.com/developers/applications)).
- Nexus must have **Message Content Intent** enabled in the Developer Portal.

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

### Version 2.0 Updates
* **Hybrid Commands:** All core, admin, moderation, and utility commands are now hybrid, meaning they support both standard prefixes (e.g., `!ban`) and Discord slash commands (e.g., `/ban`). Joke Actions and Joke Meters deliberately remain slash-only.
* **Support Ticket System:** Users can easily spawn private support tickets by clicking a button. Admins can configure the panel title, panel description, ticket category, and the specific support role pinged via the `/setup-tickets-config` UI.
* **Utility Commands:** A robust suite of owner-exclusive commands has been added to monitor bot health and perform system diagnostics (`/status`, `/uptime`, `/diagnostics`, `/server-insights`).
* **Universal UI Aesthetic:** To match modern visual standards, normal `discord.Embed` messages have all been upgraded via the `embed_factory.py`. They now utilize the `#2B2D31` color hex, which blends seamlessly into Discord's dark mode, removing the colored left-border line for a super clean "box" aesthetic!
