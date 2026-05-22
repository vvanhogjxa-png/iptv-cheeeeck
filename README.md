# Microsoft Code Checker Telegram Bot

A Telegram bot that validates Microsoft Xbox/Game Pass codes and checks their status.

## Features

✅ **Code Validation** - Check Microsoft Store codes status  
💳 **Card Detection** - Identify codes requiring payment method  
🌍 **Region Locking** - Detect region-locked codes  
📊 **Statistics** - Track valid, invalid, and redeemed codes  
🔒 **Secure** - Uses curl_cffi to bypass bot detection  
🚀 **Fast** - Multi-threaded processing  

## Status Types

- **✅ VALID** - Code is valid and can be redeemed
- **💳 VALID_REQUIRES_CARD** - Code is valid but requires a payment method on file
- **🔴 INVALID** - Code is invalid, expired, or already redeemed
- **🌍 REGION_LOCKED** - Code is region-locked for your account
- **❓ UNKNOWN** - Could not determine code status

## Installation

### Prerequisites

- Python 3.8 or higher
- pip
- Telegram Bot Token (from @BotFather)
- Microsoft Account

### Setup

1. **Clone the repository**

```bash
git clone https://github.com/vvanhogjxa-png/microsoft-code-checker.git
cd microsoft-code-checker
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Set environment variables**

```bash
# Linux/Mac
export BOT_TOKEN="your_bot_token_here"
export ADMIN_ID="your_telegram_user_id"

# Windows (PowerShell)
$env:BOT_TOKEN="your_bot_token_here"
$env:ADMIN_ID="your_telegram_user_id"
```

4. **Run the bot**

```bash
python bot.py
```

## Usage

### Getting Tokens

1. **Telegram Bot Token:**
   - Message @BotFather on Telegram
   - Use `/newbot` command
   - Follow the steps and copy the token

2. **Your Telegram User ID:**
   - Message @userinfobot on Telegram
   - It will show your user ID

### Using the Bot

1. Start the bot with `/start`
2. Click "🔍 Check Code" button
3. Send codes (one per line)
4. Send your Microsoft account (email:password)
5. Bot will check each code and report results
6. View statistics with "📊 Stats" button

## Docker Support

### Using Docker

```bash
docker build -t microsoft-code-checker .
docker run -e BOT_TOKEN="your_token" -e ADMIN_ID="your_id" microsoft-code-checker
```

### Using Docker Compose

```yaml
version: '3.8'
services:
  bot:
    build: .
    environment:
      BOT_TOKEN: "your_bot_token_here"
      ADMIN_ID: "your_telegram_user_id"
    restart: unless-stopped
```

## Security Notes

⚠️ **Important Security Warnings:**

- Never share your `BOT_TOKEN` publicly
- Never share your Microsoft credentials
- Use strong, unique passwords
- Only use trusted Microsoft accounts
- This bot is for personal use only
- Comply with Microsoft's Terms of Service

## Troubleshooting

### "Access Denied" Error
- Make sure your Telegram ID matches the `ADMIN_ID` environment variable

### "Login Failed" Error
- Verify your Microsoft email and password are correct
- Check if your account has 2FA enabled (might require app password)
- Try using an app-specific password if available

### "Rate Limited" Error
- The Microsoft account is temporarily rate-limited
- Wait 15-30 minutes before trying again
- Try with a different Microsoft account

### Connection Issues
- Check your internet connection
- Verify firewall settings
- Ensure BOT_TOKEN and ADMIN_ID are correctly set

## Performance

Average performance:
- **Speed:** 5-10 codes per second (depends on network)
- **Reliability:** ~95% successful checks
- **Rate Limit:** ~100 checks per account per hour

## API Endpoints Used

- `https://login.live.com/` - Microsoft authentication
- `https://www.microsoft.com/store/` - Store state retrieval
- `https://buynow.production.store-web.dynamics.com/` - Code validation

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Review existing GitHub issues
3. Create a new issue with detailed information

## Disclaimer

This tool is provided as-is for educational purposes. Users are responsible for:
- Complying with Microsoft's Terms of Service
- Not using stolen or unauthorized codes
- Using this tool only with legitimate Microsoft accounts
- Following all local laws and regulations

The authors are not responsible for misuse or any consequences resulting from using this tool.

## License

MIT License - See LICENSE file for details

## Credits

Created with ❤️ by [Your Name]

Telegram: @updh1
