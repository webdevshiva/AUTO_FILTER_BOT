#!/usr/bin/env python3
"""
Telegram Auto-Filter Bot - Complete Single File
With All Features: Search, Clone, Logs, Admin
"""

import os
import re
import asyncio
import logging
import hashlib
import pickle
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Any
from collections import defaultdict

# Pyrogram
from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery
)
from pyrogram.errors import UserNotParticipant

# Load Environment
from dotenv import load_dotenv
load_dotenv()

# ============================================
# CONFIGURATION
# ============================================
class Config:
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    MONGO_URL = os.getenv("MONGO_URL", "")
    ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
    LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", 0))
    FSUB_CHANNELS = list(map(int, os.getenv("FSUB_CHANNELS", "").split())) if os.getenv("FSUB_CHANNELS") else []

# ============================================
# DATABASE (Simulated - For Single File)
# ============================================
class Database:
    def __init__(self):
        self.users = {}
        self.files = []
        self.clone_bots = {}
        
    async def add_user(self, user_id, name):
        self.users[user_id] = {
            "user_id": user_id,
            "name": name,
            "joined": datetime.now(),
            "banned": False
        }
    
    async def index_file(self, file_id, file_name, chat_id, message_id, caption=""):
        self.files.append({
            "file_id": file_id,
            "file_name": file_name.lower(),
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": caption,
            "indexed_at": datetime.now()
        })
    
    async def search_files(self, query, limit=50):
        results = []
        for file in self.files:
            if query.lower() in file["file_name"]:
                results.append(file)
        return results[:limit]

# ============================================
# UTILITY CLASSES
# ============================================
class AdvancedFilter:
    def extract_metadata(self, filename):
        seasons = set()
        qualities = set()
        
        # Season
        season_match = re.search(r's(\d{1,2})', filename.lower())
        if season_match:
            seasons.add(f"S{season_match.group(1).zfill(2)}")
        
        # Quality
        quality_match = re.search(r'(\d{3,4})p', filename.lower())
        if quality_match:
            qualities.add(f"{quality_match.group(1)}p")
        
        return {"seasons": seasons, "qualities": qualities}
    
    def group_by_season(self, files):
        grouped = defaultdict(list)
        for file in files:
            metadata = self.extract_metadata(file["file_name"])
            if metadata["seasons"]:
                for season in metadata["seasons"]:
                    grouped[season].append(file)
            else:
                grouped["NO_SEASON"].append(file)
        return dict(grouped)

class HelperFunctions:
    @staticmethod
    def get_time_greeting():
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "🌅 Good Morning", "morning"
        elif 12 <= hour < 17:
            return "☀️ Good Afternoon", "afternoon"
        elif 17 <= hour < 21:
            return "🌇 Good Evening", "evening"
        else:
            return "🌙 Good Night", "night"
    
    @staticmethod
    def truncate_text(text, max_length=50):
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + "..."

class CallbackCache:
    def __init__(self):
        self.cache = {}
    
    async def store(self, user_id, data):
        key = f"cache_{user_id}_{len(self.cache)}"
        self.cache[key] = {
            "data": data,
            "user_id": user_id,
            "time": datetime.now()
        }
        return key
    
    async def retrieve(self, key, user_id=None):
        if key in self.cache:
            data = self.cache[key]
            # Check if expired (10 minutes)
            if (datetime.now() - data["time"]).seconds < 600:
                if user_id is None or data["user_id"] == user_id:
                    return data["data"]
        return None
      # ============================================
# BOT INITIALIZATION
# ============================================
app = Client(
    "auto_filter_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

# Initialize components
db = Database()
advanced_filter = AdvancedFilter()
helpers = HelperFunctions()
cache = CallbackCache()

# Global variables
PAGE_SIZE = 10
user_sessions = {}

# ============================================
# START COMMAND
# ============================================
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user = message.from_user
    
    # Add to database
    await db.add_user(user.id, user.first_name)
    
    # Get greeting
    greeting, _ = helpers.get_time_greeting()
    
    # Welcome message
    welcome_text = f"""
{greeting} **{user.first_name}!** 👋

🎬 **I'm Auto-Filter Bot**
Search movies/files in groups, get in PM!

**✨ Features:**
• 🔍 Smart search with filters
• 📁 File delivery in PM
• 🔄 Multi-bot clone system
• 🎯 Force subscribe support

Add me to a group and start searching!
"""
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add to Group", 
                url=f"https://t.me/{client.me.username}?startgroup=true"),
            InlineKeyboardButton("🌀 Clone Bot", 
                callback_data="clone_bot")
        ],
        [
            InlineKeyboardButton("📢 Updates", url="https://t.me/yourchannel"),
            InlineKeyboardButton("ℹ️ Help", callback_data="help")
        ]
    ])
    
    try:
        await message.reply_photo(
            photo="https://telegra.ph/file/8a9f2b6a6b0a8e7d5c0e3.jpg",
            caption=welcome_text,
            reply_markup=buttons
        )
    except:
        await message.reply(welcome_text, reply_markup=buttons)
    
    # Log to admin
    try:
        await client.send_message(
            Config.LOG_CHANNEL,
            f"👤 New User: {user.first_name}\n"
            f"🆔 ID: {user.id}\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except:
        pass

# ============================================
# AUTO-FILTER SEARCH
# ============================================
@app.on_message(filters.group & filters.text)
async def auto_filter(client: Client, message: Message):
    query = message.text.strip()
    if len(query) < 2:
        return
    
    user_id = message.from_user.id
    
    # Force subscribe check
    for channel in Config.FSUB_CHANNELS:
        try:
            member = await client.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                buttons = InlineKeyboardMarkup([[
                    InlineKeyboardButton("Join Channel", url=f"https://t.me/{channel}")
                ]])
                msg = await message.reply(
                    "Please join our channel first!",
                    reply_markup=buttons
                )
                await asyncio.sleep(10)
                await msg.delete()
                return
        except:
            pass
    
    # Search
    search_msg = await message.reply("🔍 Searching...")
    results = await db.search_files(query)
    
    if not results:
        await search_msg.edit("❌ No results found!")
        await asyncio.sleep(5)
        await search_msg.delete()
        return
    
    # Group by season
    season_groups = advanced_filter.group_by_season(results)
    
    if len(season_groups) > 1:
        # Show season selection
        buttons = []
        for season in sorted(season_groups.keys())[:5]:
            if season != 'NO_SEASON':
                cache_key = await cache.store(user_id, {
                    "type": "season",
                    "season": season,
                    "files": season_groups[season]
                })
                buttons.append([InlineKeyboardButton(
                    f"📂 {season}", 
                    callback_data=f"cache_{cache_key}"
                )])
        
        await search_msg.edit(
            f"**Found {len(results)} results**\nSelect season:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    else:
        # Show files directly
        await display_files(client, search_msg, results[:PAGE_SIZE], query, 0, user_id)

async def display_files(client, message, files, query, page, user_id):
    """Display files with pagination"""
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    current_files = files[start:end]
    
    if not current_files:
        await message.edit("No more files!")
        return
    
    text = f"**🔍 {query}**\n**Page {page+1}**\n\n"
    buttons = []
    
    for i, file in enumerate(current_files, start+1):
        display_name = helpers.truncate_text(file["file_name"], 40)
        
        # Store file info in cache
        cache_key = await cache.store(user_id, {
            "type": "file",
            "file_id": file["file_id"],
            "chat_id": file["chat_id"],
            "message_id": file["message_id"]
        })
        
        buttons.append([InlineKeyboardButton(
            f"📁 {i}. {display_name}",
            callback_data=f"cache_{cache_key}"
        )])
    
    # Pagination
    nav_buttons = []
    if page > 0:
        prev_cache = await cache.store(user_id, {
            "type": "page", "query": query, "files": files, "page": page-1
        })
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"cache_{prev_cache}"))
    
    if end < len(files):
        next_cache = await cache.store(user_id, {
            "type": "page", "query": query, "files": files, "page": page+1
        })
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"cache_{next_cache}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    await message.edit(text, reply_markup=InlineKeyboardMarkup(buttons))
  # ============================================
# CALLBACK QUERY HANDLER
# ============================================
@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data.startswith("cache_"):
        cache_key = data.split("_", 1)[1]
        cached = await cache.retrieve(cache_key, user_id)
        
        if not cached:
            await callback_query.answer("Session expired!", show_alert=True)
            return
        
        data_type = cached.get("type")
        
        if data_type == "file":
            # Send file to PM
            try:
                await client.copy_message(
                    chat_id=user_id,
                    from_chat_id=cached["chat_id"],
                    message_id=cached["message_id"]
                )
                await callback_query.answer("✅ File sent to PM!", show_alert=True)
            except:
                await callback_query.answer("❌ Failed to send!", show_alert=True)
            
            # Delete group message after 15s
            await asyncio.sleep(15)
            await callback_query.message.delete()
        
        elif data_type == "season":
            files = cached["files"]
            season = cached["season"]
            await display_files(client, callback_query.message, files, season, 0, user_id)
        
        elif data_type == "page":
            files = cached["files"]
            query = cached["query"]
            page = cached["page"]
            await display_files(client, callback_query.message, files, query, page, user_id)
    
    elif data == "clone_bot":
        await callback_query.message.edit(
            "**🌀 Clone Bot System**\n\n"
            "1. Go to @BotFather\n"
            "2. Create new bot\n"
            "3. Send me the token\n\n"
            "Your clone will use my database!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Back", callback_data="back")
            ]])
        )
    
    elif data == "back":
        greeting, _ = helpers.get_time_greeting()
        await callback_query.message.edit(
            f"{greeting}! What would you like to do?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("➕ Add to Group", 
                        url=f"https://t.me/{client.me.username}?startgroup=true"),
                    InlineKeyboardButton("🌀 Clone Bot", 
                        callback_data="clone_bot")
                ]
            ])
        )
    
    await callback_query.answer()

# ============================================
# ADMIN COMMANDS
# ============================================
@app.on_message(filters.command("stats") & filters.user(Config.ADMIN_ID))
async def stats_command(client, message):
    user_count = len(db.users)
    file_count = len(db.files)
    
    text = f"""
📊 **Bot Statistics**

👥 Users: {user_count}
📁 Files: {file_count}

🟢 Bot Status: Running
"""
    await message.reply(text)

@app.on_message(filters.command("index") & filters.user(Config.ADMIN_ID))
async def index_command(client, message):
    if len(message.command) < 2:
        await message.reply("Usage: /index channel_id")
        return
    
    try:
        channel_id = int(message.command[1])
        msg = await message.reply("Indexing...")
        
        count = 0
        async for msg_obj in client.iter_history(channel_id):
            if msg_obj.video or msg_obj.document:
                file_name = msg_obj.video.file_name if msg_obj.video else msg_obj.document.file_name
                file_id = msg_obj.video.file_id if msg_obj.video else msg_obj.document.file_id
                
                await db.index_file(
                    file_id=file_id,
                    file_name=file_name,
                    chat_id=channel_id,
                    message_id=msg_obj.id
                )
                count += 1
        
        await msg.edit(f"✅ Indexed {count} files!")
        
        # Log to channel
        try:
            await client.send_message(
                Config.LOG_CHANNEL,
                f"📁 Indexed {count} files from {channel_id}"
            )
        except:
            pass
        
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

# ============================================
# BOT RUNNER
# ============================================
async def main():
    await app.start()
    bot = await app.get_me()
    print(f"🤖 Bot Started: @{bot.username}")
    print("✅ All features loaded!")
    await idle()

if __name__ == "__main__":
    try:
        app.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped")
    except Exception as e:
        print(f"❌ Error: {e}")
