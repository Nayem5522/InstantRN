import os
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "your_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_token")
MONGO_URL = os.environ.get("MONGO_URL", "your_mongodb_url")

# --- DATABASE SETUP ---
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["ThumbnailBot"]
users_col = db["users"]

app = Client("InstantThumbBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- DATABASE FUNCTIONS ---
async def get_user_data(user_id):
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id,
            "caption": " {filename}",
            "current_thumb": None,
            "thumb_history": [],
            "video_history": []
        }
        await users_col.insert_one(user)
    return user

async def update_user(user_id, data):
    await users_col.update_one({"_id": user_id}, {"$set": data})

# --- START MESSAGE ---
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    await get_user_data(message.from_user.id)
    text = (
        "<b>Welcome to Instant Thumbnail Changer!</b>\n\n"
        "I can change your video thumbnail and caption instantly without downloading. "
        "Just send a photo to set it as a thumbnail, then send your video.\n\n"
        "Powered by @PrimeXBots"
    )
    buttons = [
        [InlineKeyboardButton("How to Use ❓", callback_data="help")],
        [InlineKeyboardButton("Help 💡", callback_data="help"), 
         InlineKeyboardButton("About ℹ️", callback_data="about")],
        [InlineKeyboardButton("Update Channel 📢", url="https://t.me/PrimeXBots"),
         InlineKeyboardButton("Support Group 👥", url="https://t.me/PrimeXBots")],
        [InlineKeyboardButton("Creator 👨‍💻", url="https://t.me/PrimeXBots")]
    ]
    # You can add a pic URL here
    await message.reply_photo(
        photo="https://telegra.ph/file/your_image_id.jpg", # Replace with actual image link
        caption=text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# --- SET CAPTION ---
@app.on_message(filters.command("set_caption"))
async def set_cap(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/set_caption My Video {filename} @PrimeXBots`")
    
    new_caption = message.text.split(None, 1)[1]
    await update_user(message.from_user.id, {"caption": new_caption})
    await message.reply_text(f"✅ **Custom Caption Saved:**\n`{new_caption}`")

# --- SAVE THUMBNAIL ---
@app.on_message(filters.photo)
async def save_thumbnail(client, message):
    user_id = message.from_user.id
    file_id = message.photo.file_id
    
    user = await get_user_data(user_id)
    history = user.get("thumb_history", [])
    history.insert(0, file_id) # Add to start of list
    
    # Keep only last 10 for history
    await update_user(user_id, {
        "current_thumb": file_id,
        "thumb_history": history[:10]
    })
    await message.reply_text("✅ **Thumbnail Set Successfully!**\nNow send a video.")

# --- VIDEO PROCESSING ---
@app.on_message(filters.video | filters.document)
async def process_video(client, message):
    user_id = message.from_user.id
    user = await get_user_data(user_id)
    
    if not user["current_thumb"]:
        return await message.reply_text("❌ Please send a photo first to set a thumbnail!")

    status = await message.reply_text("⚡ **Processing Instantly...**")
    
    # Handle File Name logic
    file_obj = message.video or message.document
    file_name = getattr(file_obj, 'file_name', 'video.mp4')
    
    # Format Caption
    final_caption = user["caption"].replace("{filename}", file_name)
    
    # Download thumb locally for sending (Pyrogram needs path/bio for thumb)
    thumb_path = await client.download_media(user["current_thumb"])
    
    try:
        # Save to video history
        v_history = user.get("video_history", [])
        v_history.insert(0, file_obj.file_id)
        await update_user(user_id, {"video_history": v_history[:10]})

        # Instant Send with Blur (has_spoiler)
        await client.send_video(
            chat_id=message.chat.id,
            video=file_obj.file_id,
            thumb=thumb_path,
            caption=final_caption,
            has_spoiler=True, # The "Blur" effect
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Permanent Rename? Try This Bot", url="https://t.me/Prime_Fast_Renamer_Bot")]
            ])
        )
        await status.delete()
    except Exception as e:
        await status.edit(f"Error: {e}")
    finally:
        if os.path.exists(thumb_path):
            os.remove(thumb_path)

# --- HISTORY COMMAND ---
@app.on_message(filters.command("history"))
async def history_cmd(client, message):
    buttons = [
        [InlineKeyboardButton("Show Thumbnails 🖼", callback_data="hist_thumb")],
        [InlineKeyboardButton("Show Videos 📹", callback_data="hist_video")]
    ]
    await message.reply_text("Select what you want to see from history:", reply_markup=InlineKeyboardMarkup(buttons))

# --- CALLBACK HANDLERS ---
@app.on_callback_query()
async def cb_handler(client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data
    user = await get_user_data(user_id)

    if data == "help":
        await query.message.edit_caption(
            "**How to use:**\n1. Send a photo to set it as thumbnail.\n"
            "2. Set caption using `/set_caption My File {filename}`.\n"
            "3. Send your video.\n\nAll actions are instant! @PrimeXBots",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_start")]])
        )
    
    elif data == "back_start":
        # Simplified back logic
        await query.answer("Going Back...")
        
    elif data == "hist_thumb":
        thumbs = user.get("thumb_history", [])
        if not thumbs:
            return await query.answer("No history found!", show_alert=True)
        
        btns = [[InlineKeyboardButton(f"Thumbnail {i+1}", callback_data=f"view_t_{i}")] for i in range(len(thumbs))]
        await query.message.edit_text("Your recent thumbnails (Newest first):", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("view_t_"):
        idx = int(data.split("_")[2])
        thumb_id = user["thumb_history"][idx]
        await client.send_photo(user_id, photo=thumb_id, caption="Here is your previous thumbnail.")
        await query.answer()

    elif data == "hist_video":
        videos = user.get("video_history", [])
        if not videos:
            return await query.answer("No history found!", show_alert=True)
        
        btns = [[InlineKeyboardButton(f"Video {i+1}", callback_data=f"view_v_{i}")] for i in range(len(videos))]
        await query.message.edit_text("Your recent processed videos:", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("view_v_"):
        idx = int(data.split("_")[2])
        video_id = user["video_history"][idx]
        await client.send_video(user_id, video=video_id, caption="Here is your previous video.")
        await query.answer()

app.run()
