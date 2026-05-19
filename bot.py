import os
import re
import csv
import asyncio
import requests
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN_BOT = os.getenv("TOKEN_BOT")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

HEADERS = {
    "User-Agent": "VLC/3.0.14 LibVLC/3.0.14",
    "Accept": "*/*"
}

def extract_links(text):
    links = re.findall(r'https?://[^\s"\']+', text)
    return list(dict.fromkeys(links))

def parse_account(link):
    p = urlparse(link)
    qs = parse_qs(p.query)
    username = qs.get("username", [None])[0]
    password = qs.get("password", [None])[0]
    if not username or not password:
        return None, None, None
    server = f"{p.scheme}://{p.netloc}"
    return server, username, password

def check_iptv(link):
    parsed = parse_account(link)
    if parsed[0] is None:
        return ["INVALID", "No username/password", "", "", link]

    server, username, password = parsed

    # 1) Try player_api.php
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
            if exp and str(exp).isdigit():
                exp = datetime.fromtimestamp(int(exp)).strftime("%Y-%m-%d")
            else:
                exp = "Unknown"
            conn = f"{user.get('active_cons','0')}/{user.get('max_connections','?')}"
            return [user.get("status", "UNKNOWN"), username, exp, conn, server]
    except:
        pass

    # 2) Try get.php with outputs
    for output in ["ts", "mpegts", "m3u8"]:
        try:
            r = requests.get(
                f"{server}/get.php",
                params={"username": username, "password": password, "type": "m3u_plus", "output": output},
                headers=HEADERS,
                timeout=25
            )
            if r.status_code == 200 and ("#EXTM3U" in r.text or "#EXTINF" in r.text):
                stream_test = "PLAYLIST_OK"
                streams = re.findall(r'https?://[^\s]+', r.text)
                for stream in streams[:5]:
                    try:
                        t = requests.get(stream, headers=HEADERS, timeout=10, stream=True)
                        if t.status_code in [200, 206, 302]:
                            stream_test = "STREAM_WORKING"
                            break
                        else:
                            stream_test = f"STREAM_HTTP_{t.status_code}"
                    except:
                        stream_test = "STREAM_ERROR"
                return [f"VALID_{output}", username, "Unknown", stream_test, server]
        except:
            pass

    return ["UNKNOWN_BLOCKED_OR_DEAD", username, "", "", server]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "Salam bro ✅\n"
        "Sift lia TXT file fih IPTV links, ana ncheckihom w nrj3 lik results.csv"
    )

async def handle_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    doc = update.message.document
    if not doc:
        return

    await update.message.reply_text("📥 File received. Checking IPTV links...")

    tg_file = await doc.get_file()
    await tg_file.download_to_drive("input.txt")

    with open("input.txt", "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    links = extract_links(text)
    if not links:
        await update.message.reply_text("❌ Ma l9itch IPTV links f file.")
        return

    await update.message.reply_text(f"🔍 Found {len(links)} links. Starting check...")

    results = []
    for i, link in enumerate(links, 1):
        res = await asyncio.to_thread(check_iptv, link)
        results.append(res)
        if i % 20 == 0:
            await update.message.reply_text(f"✅ Checked {i}/{len(links)}")

    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Status", "User/Error", "Expire", "Conn_or_Stream", "Server"])
        writer.writerows(results)

    await update.message.reply_document(
        open("results.csv", "rb"),
        filename="results.csv",
        caption="✅ Finished. Hadi results.csv"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text or ""
    links = extract_links(text)
    if not links:
        await update.message.reply_text("Sift TXT file ola paste IPTV links.")
        return

    await update.message.reply_text(f"🔍 Found {len(links)} links. Checking...")

    results = []
    for i, link in enumerate(links, 1):
        res = await asyncio.to_thread(check_iptv, link)
        results.append(res)
        if i % 20 == 0:
            await update.message.reply_text(f"✅ Checked {i}/{len(links)}")

    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Status", "User/Error", "Expire", "Conn_or_Stream", "Server"])
        writer.writerows(results)

    await update.message.reply_document(
        open("results.csv", "rb"),
        filename="results.csv",
        caption="✅ Finished."
    )

def main():
    if not TOKEN_BOT:
        raise RuntimeError("TOKEN_BOT missing in Railway Variables")

    app = Application.builder().token(TOKEN_BOT).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_txt))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
