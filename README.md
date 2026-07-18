<div align="center">
  <img src="assets/banner.png" alt="Nexus Banner" width="100%" />

  <br /><br />

  <img src="assets/logo.png" alt="Nexus Logo" width="150" />

  <h1>Nexus Bot</h1>

  <p><strong>A highly customizable, feature-rich Discord bot built with discord.py and SQLite.</strong></p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white&color=2b2d31" alt="Python" />
    <img src="https://img.shields.io/badge/discord.py-v2.4+-blue?style=for-the-badge&logo=discord&logoColor=white&color=2b2d31" alt="discord.py" />
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL_v3-blue?style=for-the-badge&color=2b2d31" alt="License" /></a>
  </p>

  <a href="https://discord.gg/J4SHrpcKaK">
    <img src="https://invidget.switchblade.xyz/J4SHrpcKaK" alt="Join our Discord Server" />
  </a>
  <br />
  <a href="https://discord.gg/J4SHrpcKaK">
    <img src="https://img.shields.io/badge/Discord-Join%20Support%20Server-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord Server Badge" />
  </a>
</div>

---

## 🌟 Overview

**Nexus** is an advanced Discord bot featuring an elegant, "invisible UI" aesthetic designed specifically for Discord's dark mode (`#2B2D31`). From complex ticket systems and stringent anti-nuke tools to deterministic daily joke meters and comprehensive utility commands, Nexus offers an all-in-one solution for your server's needs.

## ✨ Features

### 🎭 Dynamic Joke Meters
Measure users with daily, deterministic scoring! It provides fun progress bars and snarky commentary based on the results. The random seed is uniquely generated using the target's User ID, the meter name, and the current UTC date to keep results consistent for 24 hours.

### 🎟️ Advanced Ticket System
A highly customizable, interactive ticket UI builder. Admins can use `/ticket-setup` to create and publish multi-button ticket panels. Customize each button with its own label, emoji, specific ping role, and target category.

### 🛡️ Moderation & Automod
Protect your community with robust tools:
- Warning systems, timeout, kick, ban, and purge commands.
- AI-less Automod for fast, reliable enforcement (banned words, anti-spam, and invite blocking).

### 🛑 Anti-Nuke Systems
Rest easy knowing your server is protected against bad actors. Nexus detects and mitigates mass bans, mass kicks, channel deletions, and unauthorized role tampering.

### 🫂 Roleplay Actions
Interact with other users using `/kiss`, `/hug`, `/slap`, or `/pat` to post dynamic Giphy-powered GIFs via Slash commands.

### 🛠️ Comprehensive Utilities
Over 20 hybrid utility commands (e.g., `!avatar`, `!coinflip`, `!serverinfo`, `!math`, `!poll`) plus owner-exclusive system diagnostics (`/status`, `/uptime`, `/diagnostics`, `/server-insights`).

### 🎨 Universal Invisible UI
All Nexus embeds use `embed_factory.py` to strip away colored borders and match Discord's `#2B2D31` dark background perfectly, achieving a seamless and modern look.

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- A **Discord Bot Token** from the [Discord Developer Portal](https://discord.com/developers/applications).
- **Intents:** Nexus requires **Message Content**, **Server Members**, and **Presence** Intents to function properly.

### Setup Instructions

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/yourusername/nexus.git
   cd nexus
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the Environment:**
   Copy `.env.example` to `.env` (or create a new `.env` file) and fill in your credentials:
   ```env
   DISCORD_TOKEN=your_discord_bot_token_here
   COMMAND_PREFIX=!
   GIPHY_API_KEY=your_giphy_api_key_here
   OWNER_ID=your_discord_user_id_here
   ```

4. **Launch Nexus:**
   ```bash
   python main.py
   ```
   *Upon the first run, Nexus will automatically generate `bot_data.db` and initialize all required database tables.*

## 📄 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**. See the [LICENSE](LICENSE) file for more details.

---

<div align="center">
  <b>Built with ❤️ by the Nexus Team.</b><br />
  <a href="https://discord.gg/J4SHrpcKaK">Join our Discord community!</a>
</div>
