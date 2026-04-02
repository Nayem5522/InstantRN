import asyncio
import os
import time
import aiohttp
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "your_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_token")
MONGO_URL = os.environ.get("MONGO_URL", "your_mongo_url")
OWNER_ID = int(os.environ.get("OWNER_ID", "your_id"))
AUTH_CHANNELS = [int(ch) for ch in os.environ.get("AUTH_CHANNEL", "").split() if ch.startswith("-100")]

# --- INITIALIZATION ---
app = Client("PrimeSnapPro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["PrimeXBots_Combined"]
users_col = db["users"]

# --- HELPER FUNCTIONS ---
def small_caps(text):
    mapping = {"a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ", "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ", "s": "s", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "ʏ", "z": "ᴢ"}
    return "".join(mapping.get(c.lower(), c) for c in text)

async def get_user(user_id):
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id, 
            "caption": None, 
            "thumb": None, 
            "t_history": [], 
            "v_history": [], 
            "banned": False,
            "usage": 0
        }
        await users_col.insert_one(user)
    return user

async def is_subscribed(client, user_id):
    if user_id == OWNER_ID: return True
    for chat_id in AUTH_CHANNELS:
        try:
            await client.get_chat_member(chat_id, user_id)
        except: return False
    return True

# --- KEYBOARDS ---
def main_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ ꜱᴇᴛᴛɪɴɢꜱ", callback_data="settings_ui"), InlineKeyboardButton("📊 ʜɪꜱᴛᴏʀʏ", callback_data="history_ui")],
        [InlineKeyboardButton("📢 ᴜᴘᴅᴀᴛᴇꜱ", url="https://t.me/PrimeXBots"), InlineKeyboardButton("🎧 ꜱᴜᴘᴘᴏʀᴛ", url="https://t.me/Prime_Support_group")]
    ])

# --- START COMMAND ---
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    user = await get_user(message.from_user.id)
    if user.get("banned"): return

    if not await is_subscribed(client, message.from_user.id):
        buttons = [[InlineKeyboardButton("📢 ᴊᴏɪɴ ᴏᴜʀ ᴄʜᴀɴɴᴇʟ", url="https://t.me/PrimeXBots")]]
        buttons.append([InlineKeyboardButton("♻️ ᴛʀʏ ᴀɢᴀɪɴ", callback_data="refresh")])
        return await message.reply_text(small_caps("please join our updates channel to use me!"), reply_markup=InlineKeyboardMarkup(buttons))

    await message.reply_photo(
        photo="https://i.postimg.cc/xdkd1h4m/IMG-20250715-153124-952.jpg",
        caption=small_caps(f"welcome {message.from_user.first_name}!\nsend me any video to change its thumbnail instantly."),
        reply_markup=main_buttons()
    )

# --- VIDEO HANDLER (INSTANT THUMBNAIL CHANGER LOGIC) ---
@app.on_message(filters.video | filters.document)
async def video_handler(client, message):
    user = await get_user(message.from_user.id)
    if user["banned"]: return
    
    # Check if video
    file_obj = message.video or (message.document if message.document and message.document.mime_type.startswith("video/") else None)
    if not file_obj: return

    if not user["thumb"]:
        return await message.reply_text(small_caps("❌ please set a thumbnail first! send me a photo."))

    # Sticker logic (Optional/Premium feel)
    sticker = await message.reply_sticker("CAACAgUAAxkBAAKGfGnNPmV4Bwsx_0W1Qk8h6p3Q423nAALbEAACdYaYVO2S9fNnW52THgQ")
    
    # Instant Process Status
    status = await message.reply_text(small_caps("⚡ processing instantly..."))
    
    # Caption Logic (Main Folder System: Use original if not set)
    final_caption = user["caption"] or message.caption or ""
    
    # Download Thumbnail (Required for Pyrogram Server Upload)
    t_path = await client.download_media(user["thumb"])
    
    try:
        sent = await client.send_video(
            chat_id=message.chat.id,
            video=file_obj.file_id,
            thumb=t_path,
            caption=final_caption,
            supports_streaming=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ ꜱᴇᴛᴛɪɴɢꜱ", callback_data="settings_ui")]])
        )
        
        # History Logic
        v_hist = user.get("v_history", [])
        v_hist.insert(0, sent.video.file_id)
        await users_col.update_one(
            {"_id": message.from_user.id},
            {"$inc": {"usage": 1}, "$set": {"v_history": v_hist[:10]}}
        )
        
        await status.delete()
        await sticker.delete()
    except Exception as e:
        await status.edit(f"Error: {e}")
    finally:
        if os.path.exists(t_path): os.remove(t_path)

# --- PHOTO HANDLER ---
@app.on_message(filters.photo)
async def photo_handler(client, message):
    f_id = message.photo.file_id
    user = await get_user(message.from_user.id)
    
    t_hist = user.get("t_history", [])
    t_hist.insert(0, f_id)
    
    await users_col.update_one(
        {"_id": message.from_user.id},
        {"$set": {"thumb": f_id, "t_history": t_hist[:10]}}
    )
    await message.reply_text(small_caps("✅ thumbnail saved successfully!"))

# --- CALLBACKS (HISTORY & SETTINGS) ---
@app.on_callback_query()
async def callbacks(client, query: CallbackQuery):
    data = query.data
    u_id = query.from_user.id
    user = await get_user(u_id)

    if data == "settings_ui":
        text = f"⚙️ **ꜱᴇᴛᴛɪɴɢꜱ ᴍᴇɴᴜ**\n\n🖼 ᴛʜᴜᴍʙ: {'✅ ꜱᴇᴛ' if user['thumb'] else '❌ ɴᴏᴛ ꜱᴇᴛ'}\n📝 ᴄᴀᴘᴛɪᴏɴ: `{user['caption'] or 'ᴏʀɪɢɪɴᴀʟ'}`"
        btns = [[InlineKeyboardButton("🗑 ʀᴇᴍᴏᴠᴇ ᴛʜᴜᴍʙ", callback_data="del_thumb")], [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="home")]]
        await query.message.edit_caption(caption=small_caps(text), reply_markup=InlineKeyboardMarkup(btns))

    elif data == "history_ui":
        btns = [
            [InlineKeyboardButton("🖼 ᴛʜᴜᴍʙ ʜɪꜱᴛᴏʀʏ", callback_data="h_thumb"), InlineKeyboardButton("📹 ᴠɪᴅᴇᴏ ʜɪꜱᴛᴏʀʏ", callback_data="h_video")],
            [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="home")]
        ]
        await query.message.edit_caption(caption=small_caps("📊 **ʏᴏᴜʀ ʀᴇᴄᴇɴᴛ ᴀᴄᴛɪᴠɪᴛʏ**"), reply_markup=InlineKeyboardMarkup(btns))

    elif data == "h_thumb":
        if not user["t_history"]: return await query.answer("No History!", show_alert=True)
        # Show most recent 1
        await client.send_photo(u_id, user["t_history"][0], caption=small_caps("last saved thumbnail."))
    
    elif data == "h_video":
        if not user["v_history"]: return await query.answer("No History!", show_alert=True)
        await client.send_video(u_id, user["v_history"][0], caption=small_caps("last processed video."))

    elif data == "del_thumb":
        await users_col.update_one({"_id": u_id}, {"$set": {"thumb": None}})
        await query.answer("Thumbnail Deleted!", show_alert=True)
        await query.message.delete()

    elif data == "refresh":
        if await is_subscribed(client, u_id):
            await query.answer("Access Granted!")
            await query.message.delete()
            await start_handler(client, query.message)
        else: await query.answer("Join first!", show_alert=True)

    elif data == "home":
        await query.message.delete()
        await start_handler(client, query.message)

# --- ADMIN COMMANDS ---
@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def stats(client, message):
    total = await users_col.count_documents({})
    await message.reply(f"📊 **Total Users:** `{total}`")

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast(client, message):
    if not message.reply_to_message: return
    users = users_col.find({})
    async for u in users:
        try: await message.reply_to_message.copy(u["_id"])
        except: continue
    await message.reply("✅ Broadcast Done!")

# --- WEB SERVER (RENDER FIX) ---
async def web_server():
    app_web = web.Application()
    app_web.router.add_get("/", lambda r: web.Response(text="Bot is Active"))
    runner = web.AppRunner(app_web); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()

async def main():
    await web_server()
    await app.start()
    print("🚀 Bot Started!")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    
