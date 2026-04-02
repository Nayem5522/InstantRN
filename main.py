import asyncio
import os
import re
import time
import aiohttp
from aiohttp import web
from pyrogram import Client, filters, enums, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant, FloodWait
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION (Environment Variables) ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "your_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_token")
MONGO_URL = os.environ.get("MONGO_URL", "your_mongo_url")
OWNER_ID = int(os.environ.get("OWNER_ID", "your_id"))
# Force Sub Channels (Space separated IDs starting with -100)
AUTH_CHANNELS = [int(ch) for ch in os.environ.get("AUTH_CHANNEL", "").split() if ch.startswith("-100")]

# --- INITIALIZATION ---
app = Client("PrimeSnapThumb_Pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["PrimeXBots_Advanced"]
users_col = db["users"]

# --- UTILS / FONT HELPER ---
def small_caps(text):
    mapping = {"a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ", "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ", "s": "s", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "ʏ", "z": "ᴢ"}
    return "".join(mapping.get(c.lower(), c) for c in text)

async def get_user(user_id):
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id, 
            "caption": "<blockquote><b>{filename}</b></blockquote>\n\n⚡ ᴊᴏɪɴ: @PrimeXBots", 
            "thumb": None, 
            "t_history": [], # Array of file_ids
            "v_history": [], # Array of file_ids
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
        except UserNotParticipant: return False
        except: continue
    return True

# --- KEYBOARDS ---
def get_main_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ ꜱᴇᴛᴛɪɴɢꜱ", callback_data="settings_ui"), InlineKeyboardButton("📊 ʜɪꜱᴛᴏʀʏ", callback_data="history_ui")],
        [InlineKeyboardButton("🏆 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", callback_data="leaderboard_ui"), InlineKeyboardButton("👨‍💻 ᴅᴇᴠᴇʟᴏᴘᴇʀ", url="https://t.me/Prime_Nayem")],
        [InlineKeyboardButton("📢 ᴜᴘᴅᴀᴛᴇꜱ", url="https://t.me/PrimeXBots"), InlineKeyboardButton("🎧 ꜱᴜᴘᴘᴏʀᴛ", url="https://t.me/Prime_Support_group")]
    ])

# --- COMMANDS ---
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if user.get("banned"):
        return await message.reply_text(small_caps("❌ you are banned from using this bot."))

    if not await is_subscribed(client, user_id):
        buttons = []
        for chat_id in AUTH_CHANNELS:
            try:
                chat = await client.get_chat(chat_id)
                buttons.append([InlineKeyboardButton(f"ᴊᴏɪɴ {chat.title}", url=chat.invite_link or f"https://t.me/{chat.username}")])
            except: continue
        buttons.append([InlineKeyboardButton("♻️ ᴛʀʏ ᴀɢᴀɪɴ", callback_data="refresh_sub")])
        return await message.reply_photo(
            photo="https://i.postimg.cc/xdkd1h4m/IMG-20250715-153124-952.jpg", 
            caption=small_caps(f"hey {message.from_user.first_name}!\n\nyou must join our channels to use this bot."),
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    await message.reply_photo(
        photo="https://i.postimg.cc/xdkd1h4m/IMG-20250715-153124-952.jpg", 
        caption=small_caps(f"welcome to prime snapthumb pro!\ninstantly change video thumbnails and captions with one click."),
        reply_markup=get_main_buttons()
    )

# --- VIDEO HANDLER (ADVANCED RENAME & THUMB) ---
@app.on_message(filters.video | (filters.document & filters.create(lambda _, __, m: m.document.mime_type.startswith("video/"))))
async def video_processor(client, message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if user["banned"]: return
    if not user["thumb"]:
        return await message.reply_text(small_caps("❌ please set a thumbnail first! send a photo to me."))

    # Sticker loading logic
    sticker = await message.reply_sticker("CAACAgUAAxkBAAKGfGnNPmV4Bwsx_0W1Qk8h6p3Q423nAALbEAACdYaYVO2S9fNnW52THgQ")
    
    file_obj = message.video or message.document
    raw_name = getattr(file_obj, 'file_name', 'video.mp4')
    
    # ADVANCED RENAME: Remove extra symbols and fix spaces
    clean_name = os.path.splitext(raw_name)[0].replace("_", " ").replace(".", " ").strip()
    caption = user["caption"].replace("{filename}", clean_name)
    
    status = await message.reply_text(small_caps("⚡ processing instantly..."))
    
    # Download thumb locally for better compatibility
    t_path = await client.download_media(user["thumb"])
    
    try:
        sent = await client.send_video(
            chat_id=message.chat.id,
            video=file_obj.file_id,
            thumb=t_path,
            caption=caption,
            supports_streaming=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ ꜱᴇᴛᴛɪɴɢꜱ", callback_data="settings_ui")]])
        )
        
        # Save to History
        v_hist = user.get("v_history", [])
        v_hist.insert(0, sent.video.file_id)
        await users_col.update_one(
            {"_id": user_id}, 
            {"$inc": {"usage": 1}, "$set": {"v_history": v_hist[:10]}}
        )
        
        await status.delete()
        await sticker.delete()
    except Exception as e:
        await status.edit(f"Error: {e}")
    finally:
        if os.path.exists(t_path): os.remove(t_path)

# --- SETTINGS & PHOTO HANDLER ---
@app.on_message(filters.photo)
async def thumb_handler(client, message):
    user_id = message.from_user.id
    f_id = message.photo.file_id
    user = await get_user(user_id)
    
    # Add to History and set current
    t_hist = user.get("t_history", [])
    t_hist.insert(0, f_id)
    
    await users_col.update_one(
        {"_id": user_id}, 
        {"$set": {"thumb": f_id, "t_history": t_hist[:10]}}
    )
    await message.reply_text(small_caps("✅ thumbnail saved & added to history!"))

@app.on_message(filters.command("set_caption"))
async def set_cap(client, message):
    if len(message.command) < 2:
        return await message.reply_text(small_caps("usage: /set_caption {filename} @PrimeXBots"))
    new_cap = message.text.split(None, 1)[1]
    await users_col.update_one({"_id": message.from_user.id}, {"$set": {"caption": new_cap}})
    await message.reply_text(small_caps(f"✅ caption saved:\n\n{new_cap}"))

# --- CALLBACK QUERY (ADVANCED HISTORY UI) ---
@app.on_callback_query()
async def cb_handler(client, query: CallbackQuery):
    u_id = query.from_user.id
    data = query.data
    user = await get_user(u_id)

    if data == "refresh_sub":
        if await is_subscribed(client, u_id):
            await query.answer(small_caps("access granted!"), show_alert=True)
            await query.message.delete()
            await start_handler(client, query.message)
        else: await query.answer(small_caps("❌ still not joined!"), show_alert=True)

    elif data == "settings_ui":
        status = "✅ ꜱᴇᴛ" if user["thumb"] else "❌ ɴᴏᴛ ꜱᴇᴛ"
        text = f"⚙️ **ꜱᴇᴛᴛɪɴɢꜱ ᴍᴇɴᴜ**\n\n🖼 ᴛʜᴜᴍʙ: {status}\n📝 ᴄᴀᴘᴛɪᴏɴ: `{user['caption']}`"
        btns = [
            [InlineKeyboardButton("🖼 ᴠɪᴇᴡ ᴛʜᴜᴍʙ", callback_data="view_current_t"), InlineKeyboardButton("🗑 ᴅᴇʟᴇᴛᴇ", callback_data="del_current_t")],
            [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="back_home")]
        ]
        await query.message.edit_caption(caption=small_caps(text), reply_markup=InlineKeyboardMarkup(btns))

    elif data == "history_ui":
        btns = [
            [InlineKeyboardButton("🖼 ᴛʜᴜᴍʙ ʜɪꜱᴛᴏʀʏ", callback_data="ht_list"), InlineKeyboardButton("📹 ᴠɪᴅᴇᴏ ʜɪꜱᴛᴏʀʏ", callback_data="hv_list")],
            [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="back_home")]
        ]
        await query.message.edit_caption(caption=small_caps("📊 **ʏᴏᴜʀ ʀᴇᴄᴇɴᴛ ᴀᴄᴛɪᴠɪᴛʏ**\n(last 10 items shown)"), reply_markup=InlineKeyboardMarkup(btns))

    # --- Thumbnail History List ---
    elif data == "ht_list":
        if not user["t_history"]: return await query.answer("Empty!", show_alert=True)
        btns = []
        for i, tid in enumerate(user["t_history"]):
            btns.append([
                InlineKeyboardButton(f"🖼 ᴛʜᴜᴍʙ {i+1}", callback_data=f"show_t_{i}"),
                InlineKeyboardButton("✅ ᴜꜱᴇ", callback_data=f"use_t_{i}"),
                InlineKeyboardButton("🗑", callback_data=f"del_t_{i}")
            ])
        btns.append([InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="history_ui")])
        await query.message.edit_caption(caption=small_caps("🖼 **ᴛʜᴜᴍʙɴᴀɪʟ ʜɪꜱᴛᴏʀʏ**\nselect to use or delete."), reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("show_t_"):
        idx = int(data.split("_")[2])
        await client.send_photo(u_id, user["t_history"][idx], caption=small_caps(f"thumbnail #{idx+1} from history."))

    elif data.startswith("use_t_"):
        idx = int(data.split("_")[2])
        new_t = user["t_history"][idx]
        await users_col.update_one({"_id": u_id}, {"$set": {"thumb": new_t}})
        await query.answer("Thumbnail updated to this one!", show_alert=True)

    elif data.startswith("del_t_"):
        idx = int(data.split("_")[2])
        user["t_history"].pop(idx)
        await users_col.update_one({"_id": u_id}, {"$set": {"t_history": user["t_history"]}})
        await query.answer("Deleted from history!", show_alert=True)
        await query.message.delete()

    # --- Video History List ---
    elif data == "hv_list":
        if not user["v_history"]: return await query.answer("Empty!", show_alert=True)
        btns = []
        for i, vid in enumerate(user["v_history"]):
            btns.append([
                InlineKeyboardButton(f"📹 ᴠɪᴅᴇᴏ {i+1}", callback_data=f"get_v_{i}"),
                InlineKeyboardButton("🗑 ᴅᴇʟ", callback_data=f"del_v_{i}")
            ])
        btns.append([InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="history_ui")])
        await query.message.edit_caption(caption=small_caps("📹 **ᴠɪᴅᴇᴏ ʜɪꜱᴛᴏʀʏ**\nlast processed videos:"), reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("get_v_"):
        idx = int(data.split("_")[2])
        await query.answer("Sending video...")
        await client.send_video(u_id, user["v_history"][idx], caption=small_caps("retrieved from history."))

    elif data.startswith("del_v_"):
        idx = int(data.split("_")[2])
        user["v_history"].pop(idx)
        await users_col.update_one({"_id": u_id}, {"$set": {"v_history": user["v_history"]}})
        await query.answer("Removed from history!", show_alert=True)
        await query.message.delete()

    elif data == "leaderboard_ui":
        leaders = users_col.find({}).sort("usage", -1).limit(10)
        text = "🏆 **ᴛᴏᴘ 10 ᴜꜱᴇʀꜱ**\n\n"
        count = 1
        async for u in leaders:
            text += f"{count}. `{u['_id']}` — {u.get('usage', 0)} videos\n"
            count += 1
        await query.message.edit_caption(caption=small_caps(text), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="back_home")]]))

    elif data == "view_current_t":
        if not user["thumb"]: return await query.answer("Not set!")
        await client.send_photo(u_id, user["thumb"], caption=small_caps("your current thumbnail."))

    elif data == "del_current_t":
        await users_col.update_one({"_id": u_id}, {"$set": {"thumb": None}})
        await query.answer("Current thumbnail removed!", show_alert=True)
        await query.message.delete()

    elif data == "back_home":
        await query.message.delete()
        await start_handler(client, query.message)

# --- ADMIN PANEL ---
@app.on_message(filters.command("users") & filters.user(OWNER_ID))
async def total_users(client, message):
    total = await users_col.count_documents({})
    await message.reply_text(f"📊 **Total Users:** `{total}`")

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast_pro(client, message):
    if not message.reply_to_message: return await message.reply("Reply to a message.")
    m = await message.reply("⚡ Broadcasting...")
    users = users_col.find({})
    done = 0; failed = 0
    async for u in users:
        try:
            await message.reply_to_message.copy(u["_id"])
            done += 1
        except: failed += 1
    await m.edit(f"✅ **Broadcast Done!**\n\nSent: `{done}`\nFailed: `{failed}`")

@app.on_message(filters.command("ban") & filters.user(OWNER_ID))
async def ban_pro(client, message):
    if len(message.command) < 2: return
    u_id = int(message.command[1])
    await users_col.update_one({"_id": u_id}, {"$set": {"banned": True}})
    await message.reply(f"🚫 User `{u_id}` banned.")

# --- WEB SERVER & PINGER ---
async def web_server():
    app_web = web.Application()
    app_web.router.add_get("/", lambda r: web.Response(text="PrimeSnap Pro Active"))
    runner = web.AppRunner(app_web); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()

async def main():
    await web_server()
    await app.start()
    print("🚀 Prime Pro Bot is Online!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
    
