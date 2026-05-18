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
    """Escape special characters for Telegram MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def parse_iptv_url(raw: str):
    raw = raw.strip()
    try:
        p  = urlparse(raw)
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
    parsed = parse_iptv_url(url)
    if not parsed:
        return {"url": url, "status": "❌ Invalid URL format", "ok": False}

    base, username, password = parsed
    api_url = f"{base}/player_api.php?username={username}&password={password}"

    for attempt in range(1, retries + 1):
        try:
            kwargs = {"timeout": aiohttp.ClientTimeout(total=timeout)}
            if PROXY_URL:
                kwargs["proxy"] = PROXY_URL

            async with session.get(api_url, **kwargs) as resp:
                if resp.status != 200:
                    return {"url": url, "status": f"❌ HTTP {resp.status}", "ok": False}
                data = await resp.json(content_type=None)

                user_info   = data.get("user_info", {})
                server_info = data.get("server_info", {})

                if not user_info.get("auth", 0):
                    return {"url": url, "status": "❌ Auth failed (wrong user/pass)", "ok": False}

                status      = user_info.get("status", "unknown")
                exp_ts      = user_info.get("exp_date")
                max_conn    = user_info.get("max_connections", "?")
                active_conn = user_info.get("active_cons", "?")
                is_trial    = user_info.get("is_trial", "0")

                if exp_ts:
                    try:
                        exp_dt    = datetime.utcfromtimestamp(int(exp_ts))
                        exp_date  = exp_dt.strftime("%Y-%m-%d")
                        days_left = (exp_dt - datetime.utcnow()).days
                        if days_left < 0:
                            exp_str = f"{exp_date} (EXPIRED)"
                        elif days_left == 0:
                            exp_str = f"{exp_date} (expires TODAY)"
                        else:
                            exp_str = f"{exp_date} ({days_left}d left)"
                    except Exception:
                        exp_str = str(exp_ts)
                else:
                    exp_str = "Unlimited"

                icons = {"Active": "✅", "Expired": "❌", "Banned": "🚫"}
                status_icon = icons.get(status, "⚠️")
                server_url  = f"{server_info.get('url', base)}:{server_info.get('port', '')}"

                return {
                    "url": url, "ok": status == "Active",
                    "status": f"{status_icon} {status}",
                    "username": username, "expiry": exp_str,
                    "max_conn": max_conn, "active_conn": active_conn,
                    "is_trial": is_trial == "1", "server": server_url,
                }

        except asyncio.TimeoutError:
            if attempt < retries:
                await asyncio.sleep(2)
            continue
        except aiohttp.ClientConnectorError as e:
            return {"url": url, "status": f"🔌 Cannot connect: {str(e)[:50]}", "ok": False}
        except Exception as e:
            return {"url": url, "status": f"❌ Error: {str(e)[:60]}", "ok": False}

    return {"url": url, "status": f"⏱️ Timeout after {retries} attempts ({timeout}s each)", "ok": False}


def format_result(r: dict, index: int) -> str:
    """Format a single result using MarkdownV2 with all values escaped."""
    short_url = r['url'][:60] + "..." if len(r['url']) > 60 else r['url']

    lines = [
        esc("━━━━━━━━━━━━━━━━━━━━"),
        f"🔢 \\#{index}  `{esc(short_url)}`",
    ]

    if r.get("ok") is False and "username" not in r:
        lines.append(f"Status: {esc(r['status'])}")
    else:
        lines.append(f"Status:   {esc(r['status'])}")
        lines.append(f"User:     `{esc(str(r.get('username', '?')))}`")
        lines.append(f"Expires:  {esc(str(r.get('expiry', '?')))}")
        lines.append(f"Conns:    {esc(str(r.get('active_conn', '?')))} / {esc(str(r.get('max_conn', '?')))}")
        if r.get("is_trial"):
            lines.append("🧪 Trial account")
        lines.append(f"Server:   `{esc(str(r.get('server', '?')))}`")

    return "\n".join(lines)


def format_summary(results: list) -> str:
    total = len(results)
    ok    = sum(1 for r in results if r.get("ok"))
    return (
        f"📊 *Summary*\n"
        f"Total checked: {esc(str(total))}\n"
        f"✅ Active: {esc(str(ok))}\n"
        f"❌ Failed/Expired: {esc(str(total - ok))}"
    )


# ── handlers ───────────────────────────────────────────────────────────────

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("🚫 Access denied.")
        return
    proxy_status = "✅ Proxy active" if PROXY_URL else "⚠️ No proxy \\(direct connection\\)"
    text = (
        "👋 *IPTV Bulk Checker Bot*\n\n"
        "Send me one or more IPTV URLs \\(one per line\\) and I'll check them all\\!\n\n"
        "*Supported formats:*\n"
        "`http://host:port/get\\.php?username=X&password=Y`\n"
        "`http://host:port/player\\_api\\.php?username=X&password=Y`\n\n"
        f"Max {MAX_URLS} URLs per message\\.\n"
        f"Connection: {proxy_status}\n\n"
        "Commands:\n"
        "/start — show this help\n"
        "/status — check proxy & bot status"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("🚫 Access denied.")
        return
    if PROXY_URL:
        proxy_status = f"✅ `{esc(PROXY_URL[:40])}`"
    else:
        proxy_status = "❌ Not configured"
    text = (
        f"🤖 *Bot Status*\n\n"
        f"Proxy: {proxy_status}\n"
        f"Max URLs: {MAX_URLS}\n"
        f"Timeout: 25s × 2 retries"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def handle_urls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("🚫 Access denied.")
        return

    lines = [l.strip() for l in update.message.text.strip().splitlines() if l.strip()]
    urls  = [l for l in lines if l.startswith("http://") or l.startswith("https://")]

    if not urls:
        await update.message.reply_text(
            "⚠️ No valid URLs found\\. Each URL must start with `http://` or `https://`, one per line\\.",
            parse_mode="MarkdownV2"
        )
        return

    if len(urls) > MAX_URLS:
        await update.message.reply_text(
            f"⚠️ Too many URLs\\! Max is {MAX_URLS}\\. You sent {len(urls)}\\.",
            parse_mode="MarkdownV2"
        )
        return

    proxy_note = " via proxy 🔀" if PROXY_URL else ""
    msg = await update.message.reply_text(f"⏳ Checking {len(urls)} URL(s){proxy_note}… please wait.")

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[check_iptv(session, u) for u in urls])

    chunk, chunk_len = [], 0

    async def flush(c):
        await update.message.reply_text("\n".join(c), parse_mode="MarkdownV2")

    for i, r in enumerate(results, 1):
        block = format_result(r, i)
        if chunk_len + len(block) > 3800:
            await flush(chunk)
            chunk, chunk_len = [block], len(block)
        else:
            chunk.append(block)
            chunk_len += len(block)

    if chunk:
        await flush(chunk)

    await update.message.reply_text(format_summary(results), parse_mode="MarkdownV2")

    try:
        await msg.delete()
    except Exception:
        pass


# ── main ───────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set!")
    if not ADMIN_ID:
        raise ValueError("ADMIN_ID is not set!")

    print(f"🤖 IPTV Checker Bot starting...")
    print(f"   Admin ID : {ADMIN_ID}")
    print(f"   Proxy    : {PROXY_URL if PROXY_URL else 'None (direct)'}")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("help",   start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_urls))

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
