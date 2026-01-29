from flask import Flask
import threading
import asyncio
import os
import sys

sys.path.append('.')
from bot import app as telegram_bot

# Flask app
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "✅ Telegram Auto-Filter Bot is running!"

def run_telegram_bot():
    """Run Telegram bot with new event loop"""
    # ✅ FIX: Create new event loop for thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(telegram_bot.start())
    
    # Keep bot running
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(telegram_bot.stop())
        loop.close()

if __name__ == "__main__":
    # Start bot in separate thread
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    
    # Start Flask server
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
