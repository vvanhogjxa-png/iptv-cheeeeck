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
MAX_URLS  = 2000
HEADERS   = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}
BATCH_SIZE = 50  # check 50 at a time to avoid overload


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
    valid = [u for u in found if "username=" in u and "password=" in u]
    return list(dict.fromkeys(valid))


async def check_iptv(session: aiohttp.ClientSession, url: str, timeout: int = 25, retries: int = 2):
    parsed = parse_iptv_url(url)
    if not parsed:
        return None  # skip invalid

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
                            status = user_info.get("status", "Unknown")

                            # Only return Active lines
                            if status.lower() != "active":
                                return None

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
                                "url": url, "status": "Active",
                                "username": username, "expiry": exp_str,
                                "conn": f"{active_conn}/{max_conn}", "server": base
                            }
                        else:
                            return None  # auth failed = not active
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
                        "url": url, "status": "Active (playlist)",
                        "username": username, "expiry": "Unknown",
                        "conn": "-", "server": base
                    }
    except Exception:
        pass

    return None  # dead/blocked = skip


def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    proxy = "✅ Active" if PROXY_URL else "❌ Not set"
    await update.message.reply_text(
        f"IPTV Bulk Checker Bot\n\n"
        f"Proxy: {proxy}\n\n"
        f"How to use:\n"
        f"1. Paste URLs directly (one per line)\n"
        f"2. Send a .txt file → get a .csv with ACTIVE lines only\n\n"
        f"/status — show bot info"
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    proxy = f"Active: {PROXY_URL[:30]}..." if PROXY_URL else "Not configured"
    await update.message.reply_text(
        f"Bot Status\n"
        f"Proxy: {proxy}\n"
        f"Max URLs: {MAX_URLS}\n"
        f"Timeout: 25s x 2 retries\n"
        f"Batch size: {BATCH_SIZE}"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return

    urls = extract_urls(update.message.text)
    if not urls:
        await update.message.reply_text("No valid IPTV URLs found.")
        return
    if len(urls) > MAX_URLS:
        await update.message.reply_text(f"Too many URLs! Max is {MAX_URLS}.")
        return

    msg = await update.message.reply_text(f"Checking {len(urls)} URL(s)...")

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[check_iptv(session, u) for u in urls])

    active_results = [r for r in results if r is not None]

    if not active_results:
        await update.message.reply_text("No active lines found.")
        try: await msg.delete()
        except: pass
        return

    lines = []
    for i, r in enumerate(active_results, 1):
        block = (
            f"{'='*22}\n"
            f"#{i} ✅ {r['status']}\n"
            f"User:    {r['username']}\n"
            f"Expires: {r['expiry']}\n"
            f"Conns:   {r['conn']}\n"
            f"Server:  {r['server']}"
        )
        lines.append(block)

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

    await update.message.reply_text(
        f"Summary\n"
        f"Checked: {len(urls)}\n"
        f"Active:  {len(active_results)}\n"
        f"Failed:  {len(urls) - len(active_results)}"
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

    total = len(urls)
    await msg.edit_text(f"Found {total} URLs. Checking... (this may take a while)")

    # Process in batches and update progress
    all_results = []
    async with aiohttp.ClientSession() as session:
        for i in range(0, total, BATCH_SIZE):
            batch   = urls[i:i + BATCH_SIZE]
            results = await asyncio.gather(*[check_iptv(session, u) for u in batch])
            all_results.extend(results)
            done = min(i + BATCH_SIZE, total)
            try:
                await msg.edit_text(f"Progress: {done}/{total} checked...")
            except:
                pass

    active_results = [r for r in all_results if r is not None]

    if not active_results:
        await msg.edit_text(f"Done. No active lines found out of {total} checked.")
        return

    # Write CSV — active only
    csv_path = f"/tmp/iptv_results_{update.update_id}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Status", "Username", "Expiry", "Connections", "Server", "URL"])
        for r in active_results:
            w.writerow([r["status"], r["username"], r["expiry"], r["conn"], r["server"], r["url"]])

    await update.message.reply_document(
        document=open(csv_path, "rb"),
        filename="active_lines.csv",
        caption=(
            f"Done! Active lines only.\n"
            f"Checked: {total}\n"
            f"Active:  {len(active_results)}\n"
            f"Failed:  {total - len(active_results)}"
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
