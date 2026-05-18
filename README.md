# 🤖 IPTV Bulk Checker — Telegram Bot

Check multiple IPTV lines at once directly from Telegram. Supports Xtream Codes format.

---

## ✅ Features
- Paste up to **50 URLs at once** (one per line)
- Shows: Status, Username, Expiry date, Days remaining, Active/Max connections, Trial flag, Server
- Color-coded: ✅ Active, ❌ Expired/Failed, 🚫 Banned, ⏱️ Timeout
- Summary at the end (total / active / failed)
- Fast: all URLs are checked **in parallel**

---

## 🚀 Deploy on Railway (step by step)

### 1. Create your Telegram Bot
1. Open Telegram → search for **@BotFather**
2. Send `/newbot`
3. Follow the steps, give it a name and username
4. Copy the **Bot Token** (looks like `123456:ABCdef...`)

### 2. Push code to GitHub
1. Create a new **private** GitHub repository
2. Upload all these files:
   - `bot.py`
   - `requirements.txt`
   - `Procfile`
   - `railway.toml`

### 3. Deploy on Railway
1. Go to **https://railway.app** → sign in with GitHub
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your repository
4. Go to your project → **Variables** tab
5. Add this environment variable:
   - Key: `BOT_TOKEN`
   - Value: `your_bot_token_here` (from BotFather)
6. Railway will auto-deploy. Check **Logs** tab to confirm it says:
   ```
   🤖 IPTV Checker Bot is running...
   ```

---

## 📱 How to use the bot

1. Open your bot on Telegram
2. Send `/start` to see instructions
3. Paste your IPTV URLs, one per line, like:
   ```
   http://myserver.com:8080/get.php?username=user1&password=pass1&type=m3u_plus
   http://myserver.com:8080/player_api.php?username=user2&password=pass2
   http://anotherserver.net:80/get.php?username=abc&password=xyz
   ```
4. The bot will check all of them and reply with results + summary

---

## 🔧 Configuration

Edit `bot.py` to change:
- `MAX_URLS = 50` → max URLs per message
- `timeout=10` in `check_iptv()` → seconds to wait per server

---

## 📋 Supported URL formats

| Format | Example |
|--------|---------|
| get.php | `http://host:port/get.php?username=X&password=Y` |
| player_api | `http://host:port/player_api.php?username=X&password=Y` |

---

## ⚠️ Notes
- The bot checks the IPTV server **directly** (Xtream Codes API)
- No URLs are stored or logged
- If a server is offline or very slow, it will show as Timeout after 10 seconds
