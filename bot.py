import os
import re
import csv
import asyncio
import aiohttp
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "0"))
PROXY_URL = os.environ.get("PROXY_URL", "")
MAX_URLS  = 100
HEADERS   = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}


def parse_iptv_url(raw: str):
    raw = raw.strip()
    try:
        p  = urlparse(raw)
        qs = parse_qs(p.query)
        username = qs.get("username", [None])[0]
        password = qs.get("password", [None])[0]
        if not username or not password:
            return None
        return f"{p.scheme}://{p.netloc}", username, password
    except Exception:
        return None


def extract_urls(text: str):
    found = re.findall(r'https?://[^\s"\'<>]+', text)
    # keep only those with username= and password=
    valid = [u for u in found if "username=" in u and "password=" in u]
    return list(dict.fromkeys(valid))  # deduplicate


async def check_iptv(session: aiohttp.ClientSession, url: str, timeout: int = 25, retries: int = 2):
    parsed = parse_iptv_url(url)
    if not parsed:
        return {"url": url, "status": "INVALID", "username": "", "expiry": "", "conn": "", "server": ""}

    base, username, password = parsed
    kwargs = {"timeout": aiohttp.ClientTimeout(total=timeout), "headers": HEADERS}
    if PROXY_URL:
        kwargs["proxy"] = PROXY_URL

    # --- Try player_api.php ---
    for attempt in range(1, retries + 1):
        try:
            api_url = f"{base}/player_api.php?username={username}&password={password}"
            async with session.get(api_url, **kwargs) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    if text.strip().startswith("{"):
                        data      = await resp.json(content_type=None)
                        user_info = data.get("user_info", {})
                        if user_info.get("auth", 0):
                            status      = user_info.get("status", "Unknown")
                            exp_ts      = user_info.get("exp_date")
                            max_conn    = user_info.get("max_connections", "?")
                            active_conn = user_info.get("active_cons", "?")

                            if exp_ts and str(exp_ts).isdigit():
                                exp_dt    = datetime.utcfromtimestamp(int(exp_ts))
                                days_left = (exp_dt - datetime.utcnow()).days
                                exp_str   = exp_dt.strftime("%Y-%m-%d")
                                if days_left < 0:
                                    exp_str += " (EXPIRED)"
                                elif days_left == 0:
                                    exp_str += " (expires TODAY)"
                                else:
                                    exp_str += f" ({days_left}d left)"
                            else:
                                exp_str = "Unlimited"

                            return {
                                "url": url, "status": status,
                                "username": username, "expiry": exp_str,
                                "conn": f"{active_conn}/{max_conn}", "server": base
                            }
        except asyncio.TimeoutError:
            if attempt < retries:
                await asyncio.sleep(2)
            continue
        except Exception:
            break

    # --- Fallback: get.php ---
    try:
        get_url = f"{base}/get.php?username={username}&password={password}&type=m3u_plus"
        async with session.get(get_url, **kwargs) as resp:
            if resp.status == 200:
                text = await resp.text()
                if "#EXTM3U" in text or "#EXTINF" in text:
                    return {
                        "url": url, "status": "VALID (playlist)",
                        "username": username, "expiry": "Unknown",
                        "conn": "-", "server": base
                    }
    except Exception:
        pass

    return {
        "url": url, "status": "DEAD/BLOCKED",
        "username": username, "expiry": "", "conn": "", "server": base
    }


def status_emoji(status: str) -> str:
    s = status.upper()
    if "ACTIVE" in s:    return "✅"
    if "EXPIRED" in s:   return "❌"
    if "BANNED" in s:    return "🚫"
    if "VALID" in s:     return "⚠️"
    if "DEAD" in s:      return "💀"
    if "INVALID" in s:   return "🔴"
    return "❓"


def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    proxy = "✅ Active" if PROXY_URL else "❌ Not set"
    await update.message.reply_text(
        f"IPTV Bulk Checker Bot\n\n"
        f"Proxy: {proxy}\n\n"
        f"How to use:\n"
        f"1. Paste URLs directly (one per line) — max {MAX_URLS}\n"
        f"2. Send a .txt file with many URLs → get a .csv report\n\n"
        f"/status — show bot info"
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    proxy = f"Active: {PROXY_URL[:30]}..." if PROXY_URL else "Not configured"
    await update.message.reply_text(
        f"Bot Status\n"
        f"Proxy: {proxy}\n"
        f"Max URLs: {MAX_URLS}\n"
        f"Timeout: 25s x 2 retries"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return

    urls = extract_urls(update.message.text)
    if not urls:
        await update.message.reply_text("No valid IPTV URLs found. Make sure URLs contain username= and password=")
        return
    if len(urls) > MAX_URLS:
        await update.message.reply_text(f"Too many URLs! Max is {MAX_URLS}, you sent {len(urls)}.")
        return

    proxy_note = " via proxy" if PROXY_URL else ""
    msg = await update.message.reply_text(f"Checking {len(urls)} URL(s){proxy_note}...")

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[check_iptv(session, u) for u in urls])

    # Send results as text blocks
    lines = []
    for i, r in enumerate(results, 1):
        icon = status_emoji(r["status"])
        block = (
            f"{'='*22}\n"
            f"#{i} {icon} {r['status']}\n"
            f"User:    {r['username']}\n"
            f"Expires: {r['expiry']}\n"
            f"Conns:   {r['conn']}\n"
            f"Server:  {r['server']}"
        )
        lines.append(block)

    # Send in chunks
    chunk, chunk_len = [], 0
    for block in lines:
        if chunk_len + len(block) > 3800:
            await update.message.reply_text("\n".join(chunk))
            chunk, chunk_len = [block], len(block)
        else:
            chunk.append(block)
            chunk_len += len(block)
    if chunk:
        await update.message.reply_text("\n".join(chunk))

    # Summary
    active  = sum(1 for r in results if "active" in r["status"].lower() or "valid" in r["status"].lower())
    await update.message.reply_text(
        f"Summary\n"
        f"Total:   {len(results)}\n"
        f"Active:  {active}\n"
        f"Failed:  {len(results) - active}"
    )

    try: await msg.delete()
    except: pass


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return

    doc = update.message.document
    if not doc:
        return

    msg = await update.message.reply_text("Downloading file...")

    file     = await doc.get_file()
    tmp_path = f"/tmp/iptv_input_{update.update_id}.txt"
    await file.download_to_drive(tmp_path)

    with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    urls = extract_urls(text)
    if not urls:
        await msg.edit_text("No valid IPTV URLs found in the file.")
        return

    await msg.edit_text(f"Found {len(urls)} URLs. Checking...")

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[check_iptv(session, u) for u in urls])

    # Write CSV
    csv_path = f"/tmp/iptv_results_{update.update_id}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Status", "Username", "Expiry", "Connections", "Server", "URL"])
        for r in results:
            w.writerow([r["status"], r["username"], r["expiry"], r["conn"], r["server"], r["url"]])

    active = sum(1 for r in results if "active" in r["status"].lower() or "valid" in r["status"].lower())

    await update.message.reply_document(
        document=open(csv_path, "rb"),
        filename="iptv_results.csv",
        caption=(
            f"Done!\n"
            f"Total:  {len(results)}\n"
            f"Active: {active}\n"
            f"Failed: {len(results) - active}"
        )
    )

    try: await msg.delete()
    except: pass


def main():
    if not BOT_TOKEN: raise ValueError("BOT_TOKEN is not set!")
    if not ADMIN_ID:  raise ValueError("ADMIN_ID is not set!")

    print(f"IPTV Checker Bot starting...")
    print(f"  Admin:  {ADMIN_ID}")
    print(f"  Proxy:  {PROXY_URL or 'None'}")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("help",   start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
