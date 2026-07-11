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
TENOR_API_KEY=your_tenor_api_key_here
OWNER_ID=your_discord_user_id_here
   ```
4. **Run Nexus:**
   ```bash
   python main.py
   ```

Upon running for the first time, Nexus will automatically generate `bot_data.db` and initialize the required tables.

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0) - see the [LICENSE](LICENSE) file for details.
