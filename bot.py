import os
import requests
from curl_cffi import requests as cffi_requests
import re
import json
import time
import random
import threading
import asyncio
import urllib.parse
from datetime import datetime
import uuid
from colorama import init, Fore, Style
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
import queue
from concurrent.futures import ThreadPoolExecutor

init(autoreset=True)

# ====================== CONFIG ======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# Global state
user_sessions = {}  # Store user sessions
processing_tasks = {}  # Track running checks per user
print_lock = threading.Lock()

# States for conversation
WAITING_FOR_CODE = 1
WAITING_FOR_BATCH_SIZE = 2

def generate_reference_id(): 
    timestamp_val = int(time.time() // 30)
    n = f'{timestamp_val:08X}'
    o = (uuid.uuid4().hex + uuid.uuid4().hex).upper()
    result_chars = []
    for e in range(64):
        if e % 8 == 1:
            result_chars.append(n[(e - 1) // 8])
        else:
            result_chars.append(o[e])
    return "".join(result_chars)

def login_microsoft_account(email, password, proxies=None):
    session = cffi_requests.Session(impersonate="chrome")
    if proxies:
        session.proxies = proxies    
    try:    
        login_response = session.post(
            f"https://login.live.com/ppsecure/post.srf?username=%7bemail%7d&client_id=0000000048170EF2&contextid=072929F9A0DD49A4&opid=D34F9880C21AE341&bk=1765024327&uaid=a5b22c26bc704002ac309462e8d061bb&pid=15216&prompt=none",
            data={'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': "-Drzud3DzKKJtVD9IfM5xwJywwEjJp5zvvJmrSyu*RKOf!PbgSCQ7ReuKFS*sIpTV5r28epGtqBhqH3JYvND4!onwSWz2JEkvdeewUQC6HmAXRgjYBzSlf0mjEYbx3ULc7oy5fUK3LDSb*CnkAG03FLzwVPmT5WjYu4sE5Wqd93pCx0USJK4jelAWNvsMog0Rmj90tmeCd*1pDYjkINyPEgQSkv6y5GPuX!GmYwKccALUt*!SRaI02p*XUqePtNtJzw$$"},
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                "Cookie": "MSPRequ=id=N&lt=1765024327&co=1; uaid=a5b22c26bc704002ac309462e8d061bb; MSPOK=$uuid-90ce4cdb-2718-4d7e-9889-4136cfacc5b2; OParams=11O.DhmByHnT9kscyud7VyWQt5uWQuQOYWZ9O2v5E49mKxVoKsSZaB4KnwkAQCVjghW9A6M8syem4sO!g4KOfietehdD7U2eXeVo8eUsorIQv1deGf6v43egdNizv1*agwrVh2OTg7pu2SRE3SougNTvzlNUNe1BgtO4HFlLRm6UoEW3PNBIxuVPmFBiPs0wEU162jlfO8yA1!QZV7KKArG8NPChj0kf1IOfR95k0fIfa0!fDW8Md44pKHa3rkU0Um0KB03YEBdWMOAbJlX5RONIL3M31WhD4LG3GPAoBPAMCN9fMk2rHlwix8g6MOW3HKxDT4I0TlKrYHDBJejZWSmI23T3v2kr1MKaL9vEQoaTwOJf9VloMFBi7yB!kisHZn0BkjE!HGWhaliwYdluhJUCu1g$"
            },
            timeout=10,
            allow_redirects=False
        )
        if login_response.status_code != 302 or "error=interaction_required" in login_response.headers.get('Location', ''):
            return None, None

        token = urllib.parse.unquote(login_response.headers['Location'].split('access_token=')[1].split('&')[0])
        session.get("https://buynowui.production.store-web.dynamics.com/akam/13/79883e11")
        return session, token
        
    except Exception as e:
        return None, None

def get_store_cart_state(session, force_refresh=False, token=None):
    try:
        if force_refresh and hasattr(session, 'store_state'):
            delattr(session, 'store_state')
                
        if not force_refresh and hasattr(session, 'store_state'):
            return session.store_state
            
        ms_cv = f"xddT7qMNbECeJpTq.6.2"
        
        url = 'https://www.microsoft.com/store/purchase/buynowui/redeemnow'
        params = {
            'ms-cv': ms_cv,
            'market': 'US',
            'locale': 'en-GB',
            'clientName': 'AccountMicrosoftCom'
        }
        payload = {
            'data': '{"usePurchaseSdk":true}', 
            'market': 'US', 
            'cV': ms_cv, 
            'locale': 'en-GB', 
            'msaTicket': token, 
            'pageFormat': 'full', 
            'urlRef': 'https://account.microsoft.com/billing/redeem', 
            'isRedeem': 'true', 
            'clientType': 'AccountMicrosoftCom', 
            'layout': 'Inline', 
            'cssOverride': 'AMC', 
            'scenario': 'redeem', 
            'timeToInvokeIframe': '4977', 
            'sdkVersion': 'VERSION_PLACEHOLDER'
        }
        
        try:
            response = session.post(url, params=params, data=payload, timeout=30, allow_redirects=True)
        except Exception:
            return None
            
        text = response.text
        match = re.search(r'window\.__STORE_CART_STATE__=({.*?});', text, re.DOTALL)
        if not match:
            return None
            
        try:
            store_state = json.loads(match.group(1))
            extracted_values = {
                'ms_cv': store_state.get('appContext', {}).get('cv', ''),
                'correlation_id': store_state.get('appContext', {}).get('correlationId', ''),
                'tracking_id': store_state.get('appContext', {}).get('trackingId', ''),
                'vector_id': store_state.get('appContext', {}).get('vectorId', ''),
                'muid': store_state.get('appContext', {}).get('muid', ''),
                'alternative_muid': store_state.get('appContext', {}).get('alternativeMuid', '')
            }
            
            session.store_state = extracted_values
            return extracted_values
            
        except json.JSONDecodeError:
            return None
            
    except Exception:
        return None

async def prepare_redeem_api_call(session, code, headers, payload):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        response = await loop.run_in_executor(
            None,
            lambda: session.post(
                'https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken',
                headers=headers,
                json=payload,
                timeout=30
            )
        )
        return response
    except Exception:
        return None

async def validate_code_primary(session, code, force_refresh_ids=False, token=None):
    try:
        if not code or len(code) < 5 or ' ' in code or any(char in ['A', 'E', 'I', 'O', 'U', 'L', 'S', '0', '1', '5'] for char in code):
            return {"status": "INVALID", "message": "Invalid code format"}
        
        store_state = get_store_cart_state(session, force_refresh=force_refresh_ids, token=token)
        if not store_state:
            store_state = get_store_cart_state(session, force_refresh=True, token=token)
            if not store_state:
                return {"status": "ERROR", "message": "Failed to get store cart state"}
        
        try:
            headers = {
                "host": "buynow.production.store-web.dynamics.com",
                "connection": "keep-alive",
                "x-ms-tracking-id": store_state['tracking_id'],
                "sec-ch-ua-platform": "\"Windows\"",
                "authorization": f"WLID1.0=t={token}",
                "x-ms-client-type": "AccountMicrosoftCom",
                "x-ms-market": "US",
                "sec-ch-ua": "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
                "ms-cv": store_state['ms_cv'],
                "sec-ch-ua-mobile": "?0",
                "x-ms-reference-id": generate_reference_id(),
                "x-ms-vector-id": store_state['vector_id'],
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
                "x-ms-correlation-id": store_state['correlation_id'],
                "content-type": "application/json",
                "x-authorization-muid": store_state['alternative_muid'],
                "accept": "*/*",
                "origin": "https://www.microsoft.com",
                "sec-fetch-site": "cross-site",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "referer": "https://www.microsoft.com/",
                "accept-encoding": "gzip, deflate, br, zstd",
                "accept-language": "en-US,en;q=0.9"
            }
            payload = {
                "market": "US",
                "language": "en-US",
                "flights": ["sc_abandonedretry"],
                "tokenIdentifierValue": code,
                "supportsCsvTypeTokenOnly": False,
                "buyNowScenario": "redeem",
                "clientContext": {"client": "AccountMicrosoftCom", "deviceFamily": "Web"}
            }

            response = await prepare_redeem_api_call(session, code, headers, payload)
            
            if not response:
                return {"status": "ERROR", "message": "Request failed"}
        except Exception as e:
            return {"status": "ERROR", "message": f"Request failed: {str(e)[:50]}"}
        
        if response.status_code == 429:
            return {"status": "RATE_LIMITED", "message": "Account rate limited"}
                
        if response.status_code != 200:
            return {"status": "ERROR", "message": f"HTTP {response.status_code}"}
            
        data = response.json()

        if "tokenType" in data and data["tokenType"] == "CSV":
            value = data.get("value")
            currency = data.get("currency")
            return {"status": "BALANCE_CODE", "message": f"{value} {currency}"}
        
        if "errorCode" in data and "TooManyRequests" in data.get("errorCode", ""):
            return {"status": "RATE_LIMITED", "message": "Rate limited"}
        
        if "events" in data and "cart" in data["events"] and data["events"]["cart"]:
            cart_event = data["events"]["cart"][0]
            
            if "data" in cart_event and "reason" in cart_event["data"]:
                reason = cart_event["data"]["reason"]
                
                if "TooManyRequests" in reason:
                    return {"status": "RATE_LIMITED", "message": "Rate limited"}
                if reason == "RedeemTokenAlreadyRedeemed":
                    return {"status": "REDEEMED", "message": "Already redeemed"}
                elif reason in ["RedeemTokenExpired", "LegacyTokenAuthenticationNotProvided"]:
                    return {"status": "EXPIRED", "message": "Expired"}
                elif reason == "RedeemTokenGeoFencingError":
                    return {"status": "REGION_LOCKED", "message": "Region locked"}
                else:
                    return {"status": "INVALID", "message": reason}
        
        if "products" in data and len(data["products"]) > 0:
            product_info = data.get("productInfos", [{}])[0]
            product_id = product_info.get("productId")
            
            for product in data["products"]:
                if product.get("id") == product_id:
                    product_title = product.get("sku", {}).get("title") or product.get("title", "Unknown")
                    is_pi_required = product_info.get("isPIRequired", False)
                    
                    status_type = "VALID_REQUIRES_CARD" if is_pi_required else "VALID"
                    return {
                        "status": status_type,
                        "product_title": product_title,
                        "message": product_title
                    }
        
        return {"status": "UNKNOWN", "message": "Unknown result"}
        
    except Exception as e:
        return {"status": "ERROR", "message": f"Error: {str(e)[:50]}"}

# ====================== TELEGRAM HANDLERS ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Access Denied! Only admin can use this bot.")
        return

    keyboard = [
        [InlineKeyboardButton("🔍 Check Code", callback_data='check_code')],
        [InlineKeyboardButton("📊 Stats", callback_data='stats')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 **Microsoft Code Checker Bot**\n\n"
        "🔐 Powered by curl_cffi\n\n"
        "Choose an option:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Access Denied!", show_alert=True)
        return

    await query.answer()

    if query.data == 'check_code':
        await query.edit_message_text(
            text="📝 Send me Microsoft codes to check (one per line):",
            reply_markup=None
        )
        context.user_data['awaiting_codes'] = True
        
    elif query.data == 'stats':
        if user_id in user_sessions:
            session_data = user_sessions[user_id]
            stats_text = (
                f"📊 **Statistics**\n\n"
                f"✅ Valid: {session_data.get('valid', 0)}\n"
                f"💳 Requires Card: {session_data.get('requires_card', 0)}\n"
                f"🔴 Invalid: {session_data.get('invalid', 0)}\n"
                f"🌍 Region Locked: {session_data.get('region_locked', 0)}\n"
                f"❓ Unknown: {session_data.get('unknown', 0)}\n"
            )
        else:
            stats_text = "📊 No checks done yet."
        
        keyboard = [[InlineKeyboardButton("← Back", callback_data='back')]]
        await query.edit_message_text(
            text=stats_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif query.data == 'back':
        keyboard = [
            [InlineKeyboardButton("🔍 Check Code", callback_data='check_code')],
            [InlineKeyboardButton("📊 Stats", callback_data='stats')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="Choose an option:",
            reply_markup=reply_markup
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        return

    if context.user_data.get('awaiting_codes'):
        codes_text = update.message.text
        codes = [code.strip() for code in codes_text.split('\n') if code.strip()]
        
        if not codes:
            await update.message.reply_text("❌ No valid codes found!")
            return

        await update.message.reply_text(
            f"✅ Loaded {len(codes)} codes\n\n"
            f"Send me your Microsoft account (email:password format):"
        )
        context.user_data['codes'] = codes
        context.user_data['awaiting_account'] = True
        context.user_data['awaiting_codes'] = False

    elif context.user_data.get('awaiting_account'):
        account_text = update.message.text.strip()
        
        if ':' not in account_text:
            await update.message.reply_text("❌ Invalid format! Use email:password")
            return

        email, password = account_text.split(':', 1)
        email = email.strip()
        password = password.strip()

        await update.message.reply_text("🔄 Logging in...")
        
        session, token = login_microsoft_account(email, password)
        
        if not session or not token:
            await update.message.reply_text("❌ Login failed! Check credentials.")
            context.user_data['awaiting_account'] = False
            return

        await update.message.reply_text("✅ Logged in! Starting code check...\n\n")
        
        # Initialize user session stats
        if user_id not in user_sessions:
            user_sessions[user_id] = {
                'valid': 0,
                'requires_card': 0,
                'invalid': 0,
                'region_locked': 0,
                'unknown': 0,
                'redeemed': 0,
                'expired': 0
            }
        
        codes = context.user_data.get('codes', [])
        start_time = time.time()
        checked = 0

        for code in codes:
            try:
                result = await validate_code_primary(session, code, token=token)
                status = result.get('status', 'ERROR')

                # Update stats
                if status == 'VALID':
                    user_sessions[user_id]['valid'] += 1
                    emoji = "✅"
                elif status == 'VALID_REQUIRES_CARD':
                    user_sessions[user_id]['requires_card'] += 1
                    emoji = "💳"
                elif status == 'REGION_LOCKED':
                    user_sessions[user_id]['region_locked'] += 1
                    emoji = "🌍"
                elif status in ['REDEEMED', 'EXPIRED']:
                    user_sessions[user_id]['invalid'] += 1
                    emoji = "🔴"
                else:
                    user_sessions[user_id]['unknown'] += 1
                    emoji = "❓"

                msg = result.get('message', status)
                await update.message.reply_text(f"{emoji} {code} | {msg}")
                
                checked += 1
                
                # Rate limiting
                if checked % 5 == 0:
                    time.sleep(1)

            except Exception as e:
                await update.message.reply_text(f"⚠️ Error checking {code}: {str(e)[:50]}")

        elapsed = time.time() - start_time
        summary = (
            f"\n✅ **Check Complete!**\n\n"
            f"Total: {checked} codes\n"
            f"Time: {int(elapsed)}s\n"
            f"Speed: {checked/elapsed:.1f} codes/sec\n\n"
            f"Results:\n"
            f"✅ Valid: {user_sessions[user_id]['valid']}\n"
            f"💳 Requires Card: {user_sessions[user_id]['requires_card']}\n"
            f"🔴 Invalid: {user_sessions[user_id]['invalid']}\n"
            f"🌍 Region Locked: {user_sessions[user_id]['region_locked']}"
        )
        
        await update.message.reply_text(summary, parse_mode="Markdown")
        
        context.user_data['awaiting_account'] = False
        context.user_data['awaiting_codes'] = False

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN not set!")
        return

    if ADMIN_ID == 0:
        print("❌ ADMIN_ID not set!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(lambda update, context: print(f"Error: {context.error}"))

    print("🚀 Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
