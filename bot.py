import os
import re
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery
)
from pyrogram.errors import UserNotParticipant
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv

load_dotenv()

# ==================== CONFIG ====================
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGO_URL = os.getenv("MONGO_URL", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", 0))
FSUB_CHANNELS = [int(x) for x in os.getenv("FSUB_CHANNELS", "").split() if x]

# ==================== DATABASE ====================
try:
    mongo = MongoClient(MONGO_URL)
    db = mongo["auto_filter_bot"]
    users_col = db["users"]
    files_col = db["files"]
    clone_bots_col = db["clone_bots"]
    cache_col = db["cache"]
    print("✅ MongoDB Connected")
except ConnectionFailure:
    print("❌ MongoDB Connection Failed")
    exit(1)

# ==================== BOT CLIENT ====================
app = Client(
    "auto_filter_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ==================== UTILITY FUNCTIONS ====================
def extract_season_quality(filename: str) -> Dict:
    """Extract season and quality from filename"""
    season_match = re.search(r's(\d{1,2})', filename.lower())
    quality_match = re.search(r'(\d{3,4})p', filename.lower())
    
    return {
        "season": f"S{season_match.group(1).zfill(2)}" if season_match else None,
        "quality": f"{quality_match.group(1)}p" if quality_match else None
    }

async def check_fsub(user_id: int) -> bool:
    """Check force subscribe"""
    if not FSUB_CHANNELS:
        return True
    
    for channel in FSUB_CHANNELS:
        try:
            member = await app.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            pass
    return True

# ==================== START COMMAND ====================
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user = message.from_user
    
    # Add user to DB
    users_col.update_one(
        {"user_id": user.id},
        {"$set": {
            "first_name": user.first_name,
            "username": user.username,
            "last_active": datetime.now(),
            "banned": False
        }},
        upsert=True
    )
    
    # Welcome with photo
    welcome_text = f"""
✨ **Welcome {user.first_name}!** ✨

🎬 **Advanced Auto-Filter Bot**
All-in-one solution for movie searching!

⚡ **Features:**
• 🔍 Smart search with filters
• 📁 PM file delivery
• 🔄 Clone bot system
• 🎯 Force subscribe
• 🗂️ Season/Quality filters
• 👑 Admin panel
• 📊 Statistics

🚀 **Add me to group and type any movie name!**
"""
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add to Group", 
                url=f"https://t.me/{client.me.username}?startgroup=true"),
            InlineKeyboardButton("🌀 Clone Bot", 
                callback_data="clone_info")
        ],
        [
            InlineKeyboardButton("📢 Updates", url="https://t.me/yourchannel"),
            InlineKeyboardButton("⭐ Rate", url="https://t.me/yourchannel")
        ],
        [
            InlineKeyboardButton("👑 Admin", callback_data="admin_panel"),
            InlineKeyboardButton("📊 Stats", callback_data="stats")
        ]
    ])
    
    # Send with photo
    try:
        await message.reply_photo(
            photo="https://graph.org/file/90d4e733c8e4c53337b97.jpg",  # Change to your photo
            caption=welcome_text,
            reply_markup=buttons
        )
    except:
        await message.reply(welcome_text, reply_markup=buttons)
    
    # Log to channel
    if LOG_CHANNEL:
        try:
            await client.send_message(
                LOG_CHANNEL,
                f"👤 **New User Started**\n\n"
                f"🆔 ID: `{user.id}`\n"
                f"👤 Name: {user.first_name}\n"
                f"📛 Username: @{user.username or 'N/A'}\n"
                f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except:
            pass

# ==================== AUTO FILTER WITH BUTTONS ====================
@app.on_message(filters.group & filters.text)
async def auto_filter(client: Client, message: Message):
    query = message.text.strip()
    if len(query) < 2:
        return
    
    user_id = message.from_user.id
    
    # Force subscribe check
    if not await check_fsub(user_id):
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FSUB_CHANNELS[0]}")
        ]])
        msg = await message.reply(
            "⚠️ **Please join our channel first!**\n\n"
            "You need to subscribe to use this bot.",
            reply_markup=buttons
        )
        await asyncio.sleep(10)
        await msg.delete()
        return
    
    # Show searching
    search_msg = await message.reply("🔍 **Searching...**")
    
    # Search in DB with regex
    results = list(files_col.find(
        {"file_name": {"$regex": query, "$options": "i"}}
    ).limit(100))
    
    if not results:
        await search_msg.edit("❌ **No results found!**")
        await asyncio.sleep(5)
        await search_msg.delete()
        return
    
    # Categorize by season
    seasons = {}
    for file in results:
        metadata = extract_season_quality(file["file_name"])
        if metadata["season"]:
            if metadata["season"] not in seasons:
                seasons[metadata["season"]] = []
            seasons[metadata["season"]].append(file)
    
    # Create buttons based on results
    if len(seasons) > 1:
        # Multiple seasons - show season selection
        buttons = []
        for season in sorted(seasons.keys())[:8]:  # Max 8 seasons
            season_num = season.replace("S", "")
            callback_data = f"season_{season_num}_{query}"
            buttons.append([
                InlineKeyboardButton(
                    f"📂 {season} ({len(seasons[season])} files)",
                    callback_data=callback_data
                )
            ])
        
        await search_msg.edit(
            f"**🎬 Found {len(results)} results for '{query}'**\n\n"
            f"**Select Season:**",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif len(seasons) == 1:
        # Single season - show quality options
        season = list(seasons.keys())[0]
        files = seasons[season]
        
        # Extract qualities
        qualities = set()
        for file in files:
            metadata = extract_season_quality(file["file_name"])
            if metadata["quality"]:
                qualities.add(metadata["quality"])
        
        buttons = []
        row = []
        for quality in sorted(qualities)[:4]:  # Max 4 qualities per row
            callback_data = f"quality_{quality}_{season}_{query}"
            row.append(InlineKeyboardButton(
                f"🎚️ {quality}",
                callback_data=callback_data
            ))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        
        await search_msg.edit(
            f"**📂 {season}**\n"
            f"**Select Quality:**",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    else:
        # No season - show files directly
        await show_files_page(client, search_msg, results, query, 0)

async def show_files_page(client, message, files, query, page):
    """Show files with pagination"""
    items_per_page = 8
    start = page * items_per_page
    end = start + items_per_page
    current_files = files[start:end]
    
    total_pages = (len(files) + items_per_page - 1) // items_per_page
    
    text = f"**🔍 Results for: '{query}'**\n"
    text += f"**📄 Page {page+1}/{total_pages}**\n\n"
    
    buttons = []
    
    for i, file in enumerate(current_files, start+1):
        # Truncate filename
        display_name = file["file_name"]
        if len(display_name) > 35:
            display_name = display_name[:32] + "..."
        
        # Add quality info
        metadata = extract_season_quality(file["file_name"])
        quality_text = f" [{metadata['quality']}]" if metadata["quality"] else ""
        
        callback_data = f"send_{file['file_id']}_{file['chat_id']}_{file['message_id']}"
        
        buttons.append([
            InlineKeyboardButton(
                f"📁 {i}. {display_name}{quality_text}",
                callback_data=callback_data
            )
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("⬅️ Previous", callback_data=f"page_{page-1}_{query}")
        )
    if end < len(files):
        nav_buttons.append(
            InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}_{query}")
        )
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    await message.edit(text, reply_markup=InlineKeyboardMarkup(buttons))

# ==================== CALLBACK HANDLER ====================
@app.on_callback_query()
async def callback_handler(client: Client, callback: CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id
    
    # Force subscribe check for file sending
    if data.startswith("send_") and not await check_fsub(user_id):
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FSUB_CHANNELS[0]}")
        ]])
        await callback.message.edit(
            "⚠️ **Please join our channel first!**\n\n"
            "You need to subscribe to download files.",
            reply_markup=buttons
        )
        await callback.answer()
        return
    
    if data.startswith("send_"):
        # Send file to PM
        _, file_id, chat_id, message_id = data.split("_")
        
        try:
            await client.copy_message(
                chat_id=user_id,
                from_chat_id=int(chat_id),
                message_id=int(message_id)
            )
            await callback.answer("✅ File sent to your PM!", show_alert=True)
        except Exception as e:
            await callback.answer("❌ Failed to send file!", show_alert=True)
        
        # Delete group message after 15s
        await asyncio.sleep(15)
        await callback.message.delete()
    
    elif data.startswith("season_"):
        # Season selected
        _, season_num, query = data.split("_", 2)
        season = f"S{season_num.zfill(2)}"
        
        # Search files for this season
        results = list(files_col.find({
            "file_name": {"$regex": query, "$options": "i"},
            "file_name": {"$regex": f"season {season_num}|s{season_num}", "$options": "i"}
        }))
        
        if results:
            await show_files_page(client, callback.message, results, f"{query} - {season}", 0)
        else:
            await callback.answer("No files found!", show_alert=True)
    
    elif data.startswith("quality_"):
        # Quality selected
        _, quality, season, query = data.split("_", 3)
        
        # Search files with this quality
        results = list(files_col.find({
            "file_name": {"$regex": query, "$options": "i"},
            "file_name": {"$regex": quality, "$options": "i"}
        }))
        
        if results:
            await show_files_page(client, callback.message, results, f"{query} - {quality}", 0)
        else:
            await callback.answer("No files found!", show_alert=True)
    
    elif data.startswith("page_"):
        # Pagination
        _, page_str, query = data.split("_", 2)
        page = int(page_str)
        
        results = list(files_col.find(
            {"file_name": {"$regex": query, "$options": "i"}}
        ))
        
        if results:
            await show_files_page(client, callback.message, results, query, page)
        else:
            await callback.answer("No results!", show_alert=True)
    
    elif data == "clone_info":
        # Clone bot info
        await callback.message.edit(
            "**🌀 Clone Bot System**\n\n"
            "Create your own bot with my database!\n\n"
            "**Steps:**\n"
            "1. Go to @BotFather\n"
            "2. Create new bot\n"
            "3. Send me the token\n\n"
            "**Features your clone will have:**\n"
            "• Same database\n"
            "• All search features\n"
            "• Force subscribe\n"
            "• 24/7 hosting\n\n"
            "Send your bot token now:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="back_to_start")
            ]])
        )
    
    elif data == "admin_panel":
        if user_id == ADMIN_ID:
            total_users = users_col.count_documents({})
            total_files = files_col.count_documents({})
            
            await callback.message.edit(
                f"**👑 Admin Panel**\n\n"
                f"👥 Users: {total_users}\n"
                f"📁 Files: {total_files}\n"
                f"🤖 Bot: @{client.me.username}\n\n"
                f"**Commands:**\n"
                f"/index - Index channel\n"
                f"/stats - Statistics\n"
                f"/broadcast - Send message\n"
                f"/logs - View logs",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("📊 Stats", callback_data="stats"),
                        InlineKeyboardButton("📢 Broadcast", callback_data="broadcast_menu")
                    ],
                    [
                        InlineKeyboardButton("🔙 Back", callback_data="back_to_start")
                    ]
                ])
            )
        else:
            await callback.answer("❌ Admin only!", show_alert=True)
    
    elif data == "stats":
        total_users = users_col.count_documents({})
        total_files = files_col.count_documents({})
        
        await callback.message.edit(
            f"**📊 Bot Statistics**\n\n"
            f"👥 Total Users: {total_users}\n"
            f"📁 Total Files: {total_files}\n"
            f"🔄 MongoDB: Connected\n"
            f"⚡ Status: Running\n"
            f"🤖 Username: @{client.me.username}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="back_to_start")
            ]])
        )
    
    elif data == "back_to_start":
        user = callback.from_user
        await callback.message.edit(
            f"✨ **Welcome back {user.first_name}!**\n\n"
            "Ready to search movies?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("➕ Add to Group", 
                        url=f"https://t.me/{client.me.username}?startgroup=true"),
                    InlineKeyboardButton("🌀 Clone Bot", 
                        callback_data="clone_info")
                ],
                [
                    InlineKeyboardButton("👑 Admin", callback_data="admin_panel"),
                    InlineKeyboardButton("📊 Stats", callback_data="stats")
                ]
            ])
        )
    
    await callback.answer()

# ==================== CLONE BOT TOKEN HANDLER ====================
@app.on_message(filters.private & filters.regex(r'^\d+:[\w-]+$'))
async def handle_token(client: Client, message: Message):
    """Handle clone bot token"""
    token = message.text.strip()
    user_id = message.from_user.id
    
    # Save to database
    clone_bots_col.update_one(
        {"user_id": user_id},
        {"$set": {
            "token": token,
            "created_at": datetime.now(),
            "owner": message.from_user.first_name,
            "active": True
        }},
        upsert=True
    )
    
    await message.reply(
        "✅ **Clone bot created successfully!**\n\n"
        "Your clone bot will:\n"
        "• Use the same database\n"
        "• Have all features\n"
        "• Work 24/7\n\n"
        "Start your bot by visiting:\n"
        f"https://t.me/BotFather\n\n"
        "**Token saved securely!**"
    )
    
    # Log to channel
    if LOG_CHANNEL:
        try:
            await client.send_message(
                LOG_CHANNEL,
                f"🌀 **New Clone Bot Created**\n\n"
                f"👤 Owner: {message.from_user.mention}\n"
                f"🆔 ID: `{user_id}`\n"
                f"🤖 Token: `{token[:15]}...`\n"
                f"📅 Time: {datetime.now().strftime('%H:%M:%S')}"
            )
        except:
            pass

# ==================== ADMIN COMMANDS ====================
@app.on_message(filters.command("index") & filters.user(ADMIN_ID))
async def index_channel(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("Usage: `/index channel_id`", quote=True)
        return
    
    try:
        channel_id = int(message.command[1])
        status = await message.reply("⏳ **Indexing started...**")
        
        count = 0
        async for msg in client.iter_history(channel_id):
            if msg.video or msg.document:
                file_name = msg.video.file_name if msg.video else msg.document.file_name
                file_id = msg.video.file_id if msg.video else msg.document.file_id
                
                files_col.update_one(
                    {"file_id": file_id},
                    {"$set": {
                        "file_id": file_id,
                        "file_name": file_name.lower(),
                        "chat_id": channel_id,
                        "message_id": msg.id,
                        "caption": msg.caption or "",
                        "indexed_at": datetime.now()
                    }},
                    upsert=True
                )
                count += 1
        
        await status.edit(f"✅ **Indexed {count} files!**")
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast_message(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply("Reply to a message to broadcast!", quote=True)
        return
    
    users = users_col.find({})
    total = users_col.count_documents({})
    
    status = await message.reply(f"📢 Broadcasting to {total} users...")
    
    success = 0
    failed = 0
    
    for user in users:
        try:
            await client.copy_message(
                chat_id=user["user_id"],
                from_chat_id=message.chat.id,
                message_id=message.reply_to_message.id
            )
            success += 1
            await asyncio.sleep(0.1)  # Avoid flood
        except:
            failed += 1
    
    await status.edit(f"✅ **Broadcast Complete!**\n\n✅ Success: {success}\n❌ Failed: {failed}")

# ==================== BOT RUNNER ====================
async def main():
    await app.start()
    bot = await app.get_me()
    
    print("="*50)
    print(f"🤖 BOT STARTED: @{bot.username}")
    print(f"👥 Users: {users_col.count_documents({})}")
    print(f"📁 Files: {files_col.count_documents({})}")
    print(f"🔄 MongoDB: Connected")
    print(f"⚡ Force Sub: {'Enabled' if FSUB_CHANNELS else 'Disabled'}")
    print(f"👑 Admin: {ADMIN_ID}")
    print("="*50)
    print("✅ Bot is now running!")
    print("="*50)
    
    await idle()

if __name__ == "__main__":
    try:
        app.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
