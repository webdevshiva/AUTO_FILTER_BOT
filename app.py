from flask import Flask
import threading
import os
import sys

sys.path.append('.')
from bot import app as telegram_bot

# Flask app for port binding
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "✅ Telegram Auto-Filter Bot is running!"

@web_app.route('/health')
def health_check():
    return "OK", 200

def run_telegram_bot():
    """Run Telegram bot"""
    telegram_bot.run()

if __name__ == "__main__":
    # Start Telegram bot in background thread
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    
    # Start Flask web server (for port binding)
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)
