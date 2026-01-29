from flask import Flask
import threading
import os

# Flask app banao
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "✅ Bot is running on Render!"

@web_app.route('/health')
def health():
    return "OK", 200

def run_telegram_bot():
    """Telegram bot chalao"""
    from bot import app
    app.run()

if __name__ == "__main__":
    # Telegram bot start karo (background mein)
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    
    # Flask server start karo (PORT binding ke liye)
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)
