import os
import asyncio
import aiohttp
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from urllib.parse import urlparse, parse_qs

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "")
ADMIN_ID   = int(os.environ.get("ADMIN_ID", "0"))
PROXY_URL  = os.environ.get("PROXY_URL", "")
MAX_URLS   = 50


# ── helpers ────────────────────────────────────────────────────────────────

def esc(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""import os, re, csv, asyncio, requests
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}

def clean_links(text):
    found = re.findall(r'https?://[^\s"\']+', text)
    return list(dict.fromkeys(found))

def check_link(link):
    p = urlparse(link)
    qs = parse_qs(p.query)
    username = qs.get("username", [None])[0]
    password = qs.get("password", [None])[0]

    if not username or not password:
        return ["INVALID", "No user/pass", "", "", link]

    server = f"{p.scheme}://{p.netloc}"

    # 1 player_api.php
    try:
        r = requests.get(
            f"{server}/player_api.php",
            params={"username": username, "password": password},
            headers=HEADERS,
            timeout=20
        )
        if r.status_code == 200 and r.text.strip().startswith("{"):
            data = r.json()
            user = data.get("user_info", {})
            exp = user.get("exp_date")
            exp = datetime.fromtimestamp(int(exp)).strftime("%Y-%m-%d") if exp and str(exp).isdigit() else "Unknown"
            conn = f"{user.get('active_cons','0')}/{user.get('max_connections','?')}"
            return [user.get("status", "UNKNOWN"), username, exp, conn, server]
    except:
        pass

    # 2 get.php multiple outputs
    for output in ["ts", "mpegts", "m3u8"]:
        try:
            r = requests.get(
                f"{server}/get.php",
                params={
                    "username": username,
                    "password": password,
                    "type": "m3u_plus",
                    "output": output
                },
                headers=HEADERS,
                timeout=25
            )

            if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXTINF" in r.text):
                stream_status = "PLAYLIST_OK"

                streams = re.findall(r'https?://[^\s]+', r.text)
                for s in streams[:3]:
                    try:
                        t = requests.get(s, headers=HEADERS, timeout=10, stream=True)
                        if t.status_code in [200, 206, 302]:
                            stream_status = "STREAM_WORKING"
                            break
                    except:
                        pass

                return [f"VALID_{output}", username, "Unknown", stream_status, server]

        except:
            pass

    return ["UNKNOWN_BLOCKED_OR_DEAD", username, "", "", server]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Send me txt file فيه IPTV links.")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    doc = update.message.document
    if not doc:
        return

    await update.message.reply_text("Checking links...")

    file = await doc.get_file()
    await file.download_to_drive("input.txt")

    with open("input.txt", "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    links = clean_links(text)
    results = []

    for i, link in enumerate(links, 1):
        res = await asyncio.to_thread(check_link, link)
        results.append(res)

        if i % 20 == 0:
            await update.message.reply_text(f"Checked {i}/{len(links)}")

    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Status", "User/Error", "Expire", "Conn_or_Stream", "Server"])
        w.writerows(results)

    await update.message.reply_document(open("results.csv", "rb"), filename="results.csv")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
