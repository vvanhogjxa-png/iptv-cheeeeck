import os
import asyncio
import aiohttp
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from urllib.parse import urlparse, parse_qs

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
MAX_URLS = 50  # max URLs per batch


# ── helpers ────────────────────────────────────────────────────────────────

def parse_iptv_url(raw: str):
    """
    Accept two formats:
      1. http://host:port/get.php?username=X&password=Y&type=...
      2. http://host:port/player_api.php?username=X&password=Y
    Returns (base, username, password) or None on failure.
    """
    raw = raw.strip()
    try:
        p = urlparse(raw)
        qs = parse_qs(p.query)
        username = qs.get("username", [None])[0]
        password = qs.get("password", [None])[0]
        if not username or not password:
            return None
        base = f"{p.scheme}://{p.netloc}"
        return base, username, password
    except Exception:
        return None


async def check_iptv(session: aiohttp.ClientSession, url: str, timeout: int = 25, retries: int = 2):
    """
    Call the Xtream Codes player_api.php and return a result dict.
    Retries up to `retries` times on timeout or connection error.
    """
    parsed = parse_iptv_url(url)
    if not parsed:
        return {"url": url, "status": "❌ Invalid URL format", "ok": False}

    base, username, password = parsed
    api_url = f"{base}/player_api.php?username={username}&password={password}"

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    return {"url": url, "status": f"❌ HTTP {resp.status}", "ok": False}
                data = await resp.json(content_type=None)

                user_info = data.get("user_info", {})
                server_info = data.get("server_info", {})

                auth = user_info.get("auth", 0)
                if not auth:
                    return {"url": url, "status": "❌ Auth failed (wrong user/pass)", "ok": False}

                status = user_info.get("status", "unknown")
                exp_ts = user_info.get("exp_date")
                max_conn = user_info.get("max_connections", "?")
                active_conn = user_info.get("active_cons", "?")
                is_trial = user_info.get("is_trial", "0")

                # expiry
                if exp_ts:
                    try:
                        exp_date = datetime.utcfromtimestamp(int(exp_ts)).strftime("%Y-%m-%d")
                        now = datetime.utcnow()
                        diff = datetime.utcfromtimestamp(int(exp_ts)) - now
                        days_left = diff.days
                        if days_left < 0:
                            exp_str = f"{exp_date} (⚠️ EXPIRED)"
                        elif days_left == 0:
                            exp_str = f"{exp_date} (⚠️ expires TODAY)"
                        else:
                            exp_str = f"{exp_date} ({days_left}d left)"
                    except Exception:
                        exp_str = str(exp_ts)
                else:
                    exp_str = "Unlimited"

                # status emoji
                if status == "Active":
                    status_icon = "✅"
                elif status == "Expired":
                    status_icon = "❌"
                elif status == "Banned":
                    status_icon = "🚫"
                else:
                    status_icon = "⚠️"

                server_url = f"{server_info.get('url', base)}:{server_info.get('port', '')}"

                return {
                    "url": url,
                    "ok": status == "Active",
                    "status": f"{status_icon} {status}",
                    "username": username,
                    "expiry": exp_str,
                    "max_conn": max_conn,
                    "active_conn": active_conn,
                    "is_trial": is_trial == "1",
                    "server": server_url,
                }

        except asyncio.TimeoutError:
            last_error = f"⏱️ Timeout after {timeout}s"
            if attempt < retries:
                await asyncio.sleep(2)
            continue
        except aiohttp.ClientConnectorError:
            return {"url": url, "status": "🔌 Cannot connect to server", "ok": False}
        except Exception as e:
            return {"url": url, "status": f"❌ Error: {str(e)[:60]}", "ok": False}

    return {"url": url, "status": f"⏱️ Timeout after {retries} attempts ({timeout}s each)", "ok": False}


def format_result(r: dict, index: int) -> str:
    lines = [f"━━━━━━━━━━━━━━━━━━━━", f"🔢 #{index}  `{r['url'][:60]}...`" if len(r['url']) > 60 else f"🔢 #{index}  `{r['url']}`"]

    if r.get("ok") is False and "username" not in r:
        lines.append(f"Status: {r['status']}")
    else:
        lines.append(f"Status:     {r['status']}")
        lines.append(f"User:       `{r.get('username', '?')}`")
        lines.append(f"Expires:    {r.get('expiry', '?')}")
        lines.append(f"Conns:      {r.get('active_conn', '?')} / {r.get('max_conn', '?')}")
        if r.get("is_trial"):
            lines.append("🧪 Trial account")
        lines.append(f"Server:     `{r.get('server', '?')}`")

    return "\n".join(lines)


def format_summary(results: list) -> str:
    total = len(results)
    ok = sum(1 for r in results if r.get("ok"))
    bad = total - ok
    return (
        f"📊 *Summary*\n"
        f"Total checked: {total}\n"
        f"✅ Active: {ok}\n"
        f"❌ Failed/Expired: {bad}"
    )


# ── handlers ───────────────────────────────────────────────────────────────

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("🚫 Access denied.")
        return
    text = (
        "👋 *IPTV Bulk Checker Bot*\n\n"
        "Send me one or more IPTV URLs (one per line) and I'll check them all!\n\n"
        "*Supported formats:*\n"
        "`http://host:port/get.php?username=X&password=Y`\n"
        "`http://host:port/player_api.php?username=X&password=Y`\n\n"
        f"Max {MAX_URLS} URLs per message.\n\n"
        "Commands:\n"
        "/start — show this help\n"
        "/help — show this help"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("🚫 Access denied.")
        return
    await start(update, context)


async def handle_urls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("🚫 Access denied.")
        return
    text = update.message.text.strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # filter lines that look like URLs
    urls = [l for l in lines if l.startswith("http://") or l.startswith("https://")]

    if not urls:
        await update.message.reply_text(
            "⚠️ No valid URLs found. Make sure each URL starts with `http://` or `https://` and is on its own line.",
            parse_mode="Markdown"
        )
        return

    if len(urls) > MAX_URLS:
        await update.message.reply_text(f"⚠️ Too many URLs! Max is {MAX_URLS}. You sent {len(urls)}.")
        return

    msg = await update.message.reply_text(f"⏳ Checking {len(urls)} URL(s)… please wait.")

    async with aiohttp.ClientSession() as session:
        tasks = [check_iptv(session, u) for u in urls]
        results = await asyncio.gather(*tasks)

    # send results in chunks to avoid Telegram 4096-char limit
    chunk = []
    chunk_len = 0

    async def flush(chunk):
        body = "\n".join(chunk)
        await update.message.reply_text(body, parse_mode="Markdown")

    for i, r in enumerate(results, 1):
        block = format_result(r, i)
        if chunk_len + len(block) > 3800:
            await flush(chunk)
            chunk = [block]
            chunk_len = len(block)
        else:
            chunk.append(block)
            chunk_len += len(block)

    if chunk:
        await flush(chunk)

    # summary
    summary = format_summary(results)
    await update.message.reply_text(summary, parse_mode="Markdown")

    # delete the "checking" message
    try:
        await msg.delete()
    except Exception:
        pass


# ── main ───────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set!")
    if not ADMIN_ID:
        raise ValueError("ADMIN_ID environment variable is not set!")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_urls))

    print(f"🤖 IPTV Checker Bot is running... (admin: {ADMIN_ID})")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
