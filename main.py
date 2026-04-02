import asyncio
import os
import re
import time
import aiohttp
from aiohttp import web
from datetime import datetime

# --- CRITICAL: EVENT LOOP FIX ---
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client, filters, enums, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant, FloodWait
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIG ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "your_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_token")
MONGO_URL = os.environ.get("MONGO_URL", "your_mongo_url")
OWNER_ID = int(os.environ.get("OWNER_ID", "your_id"))
AUTH_CHANNELS = [int(ch) for ch in os.environ.get("AUTH_CHANNEL", "").split() if ch.startswith("-100")]

app = Client("PrimeSnapThumb", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["PrimeXBots_Combined"]
users_col = db["users"]
settings_col = db["settings"]

# --- FONT HELPER ---
def small_caps(text):
    mapping = {"a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ", "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ", "s": "s", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "ʏ", "z": "ᴢ"}
    return "".join(mapping.get(c.lower(), c) for c in text)

# --- DATABASE LOGIC ---
async def get_user(user_id):
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id, 
            "caption": "{filename}", 
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
        except UserNotParticipant: return False
        except: continue
    return True

# --- UI BUTTONS ---
def get_start_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("〆 ʜᴇʟᴘ 〆", callback_data="help_ui"), InlineKeyboardButton("〆 ᴀʙᴏᴜᴛ 〆", callback_data="about_ui")],
        [InlineKeyboardButton("〄 ᴜᴘᴅᴀᴛᴇs ᴄʜᴀɴɴᴇʟ 〄", url="https://t.me/PrimeXBots"), InlineKeyboardButton("✪ ꜱᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ ✪", url="https://t.me/Prime_Support_group")],
        [InlineKeyboardButton("✧ ᴄʀᴇᴀᴛᴏʀ ✧", url="https://t.me/Prime_Nayem")]
    ])

# --- COMMANDS ---
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if user.get("banned"):
        return await message.reply_text("❌ You are banned from using this bot.")

    if not await is_subscribed(client, user_id):
        buttons = []
        for chat_id in AUTH_CHANNELS:
            chat = await client.get_chat(chat_id)
            buttons.append([InlineKeyboardButton(f"✇ ᴊᴏɪɴ {chat.title} ✇", url=chat.invite_link)])
        buttons.append([InlineKeyboardButton("♻️ ʀᴇғʀᴇsʜ ♻️", callback_data="refresh_sub")])
        return await message.reply_photo(photo="https://i.postimg.cc/xdkd1h4m/IMG-20250715-153124-952.jpg", 
            caption=f"👋 Hello {message.from_user.mention},\n\nYou must join our updates channel to use me.", reply_markup=InlineKeyboardMarkup(buttons))

    await message.reply_photo(photo="https://i.postimg.cc/xdkd1h4m/IMG-20250715-153124-952.jpg", 
        caption=small_caps("welcome to prime snapthumb bot! instantly update thumbnails and captions."), reply_markup=get_start_buttons())

# --- ADMIN COMMANDS ---
@app.on_message(filters.command("users") & filters.user(OWNER_ID))
async def users_stats(client, message):
    total = await users_col.count_documents({})
    await message.reply_text(f"📊 **Total Users:** `{total}`")

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast_cmd(client, message):
    if not message.reply_to_message:
        return await message.reply_text("Reply to a message to broadcast.")
    
    msg = await message.reply_text("⚡ Broadcasting...")
    users = users_col.find({})
    done = 0; failed = 0
    async for user in users:
        try:
            await message.reply_to_message.copy(user["_id"])
            done += 1
        except: failed += 1
    await msg.edit(f"✅ **Broadcast Done!**\n\nSent: `{done}`\nFailed: `{failed}`")

@app.on_message(filters.command("ban") & filters.user(OWNER_ID))
async def ban_user(client, message):
    if len(message.command) < 2: return
    u_id = int(message.command[1])
    await users_col.update_one({"_id": u_id}, {"$set": {"banned": True}})
    await message.reply_text(f"🚫 User `{u_id}` banned.")

@app.on_message(filters.command("unban") & filters.user(OWNER_ID))
async def unban_user(client, message):
    if len(message.command) < 2: return
    u_id = int(message.command[1])
    await users_col.update_one({"_id": u_id}, {"$set": {"banned": False}})
    await message.reply_text(f"✅ User `{u_id}` unbanned.")

@app.on_message(filters.command("topleaderboard"))
async def leaderboard(client, message):
    leaders = users_col.find({}).sort("usage", -1).limit(10)
    text = "🏆 **Top 10 Users:**\n\n"
    async for u in leaders:
        text += f"👤 `{u['_id']}` — {u['usage']} videos\n"
    await message.reply_text(text)

# --- SETTINGS ---
@app.on_message(filters.command("set_caption"))
async def set_cap(client, message):
    if len(message.command) < 2: return await message.reply_text("Usage: `/set_caption {filename} @PrimeXBots`")
    new_cap = message.text.split(None, 1)[1]
    await users_col.update_one({"_id": message.from_user.id}, {"$set": {"caption": new_cap}})
    await message.reply_text(f"✅ **ᴄᴀᴘᴛɪᴏɴ sᴀᴠᴇᴅ:**\n`{new_cap}`")

@app.on_message(filters.photo)
async def save_thumb(client, message):
    f_id = message.photo.file_id
    u = await get_user(message.from_user.id)
    hist = u.get("t_history", [])
    hist.insert(0, f_id)
    await users_col.update_one({"_id": message.from_user.id}, {"$set": {"thumb": f_id, "t_history": hist[:10]}})
    await message.reply_text(small_caps("✅ thumbnail saved!"))

# --- PROCESSING ---
@app.on_message(filters.video | filters.document)
async def video_handler(client, message):
    user = await get_user(message.from_user.id)
    if user.get("banned"): return
    if not user["thumb"]: return await message.reply_text(small_caps("❌ please set a thumbnail first!"))

    # Sticker logic
    sticker = await message.reply_sticker("CAACAgUAAxkBAAKGfGnNPmV4Bwsx_0W1Qk8h6p3Q423nAALbEAACdYaYVO2S9fNnW52THgQ")
    await asyncio.sleep(4)
    await sticker.delete()

    file_obj = message.video or message.document
    raw_name = getattr(file_obj, 'file_name', 'video.mp4')
    # Clean name logic (Rename like that bot)
    clean_name = os.path.splitext(raw_name)[0].replace("_", " ").replace(".", " ")
    
    caption = user["caption"].replace("{filename}", clean_name)
    status = await message.reply_text(small_caps("⚡ processing instantly..."))
    
    # Download thumb to force server update (Instant but reliable)
    t_path = await client.download_media(user["thumb"])
    
    try:
        await client.send_video(
            chat_id=message.chat.id,
            video=file_obj.file_id,
            thumb=t_path,
            caption=caption,
            supports_streaming=True
        )
        # Usage & History
        v_hist = user.get("v_history", [])
        v_hist.insert(0, file_obj.file_id)
        await users_col.update_one({"_id": message.from_user.id}, {"$inc": {"usage": 1}, "$set": {"v_history": v_hist[:10]}})
        await status.delete()
    except Exception as e:
        await status.edit(f"Error: {e}")
    finally:
        if os.path.exists(t_path): os.remove(t_path)

# --- CALLBACKS ---
@app.on_callback_query()
async def cb_handler(client, query: CallbackQuery):
    u_id = query.from_user.id
    data = query.data
    me = await client.get_me()

    if data == "refresh_sub":
        if await is_subscribed(client, u_id):
            await query.answer("ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴊᴏɪɴɪɴɢ!", show_alert=True)
            await query.message.delete()
            await start_handler(client, query.message)
        else: await query.answer("⚠️ ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴊᴏɪɴᴇᴅ ʏᴇᴛ!", show_alert=True)

    elif data == "help_ui":
        h_text = "**ʜᴏᴡ ᴛᴏ ᴜsᴇ:**\n1. Send a photo.\n2. Set /set_caption.\n3. Send video.\n\n||@Prime_Fast_Renamer_Bot||"
        await query.message.edit_caption(caption=small_caps(h_text), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="back_home")]]))

    elif data == "about_ui":
        about_text = (
            f"<b><blockquote>⍟───[  <a href='https://t.me/PrimeXBots'>ᴍʏ ᴅᴇᴛᴀɪʟꜱ ʙʏ ᴘʀɪᴍᴇXʙᴏᴛꜱ</a> ]───⍟</blockquote></b>\n\n"
            f"‣ ᴍʏ ɴᴀᴍᴇ : <a href='https://t.me/{me.username}'>{me.first_name}</a>\n"
            "‣ ʙᴇꜱᴛ ꜰʀɪᴇɴᴅ : <a href='tg://settings'>ᴛʜɪꜱ ᴘᴇʀꜱᴏɴ</a>\n"
            "‣ ᴅᴇᴠᴇʟᴏᴘᴇʀ : <a href='https://t.me/Prime_Nayem'>ᴍʀ.ᴘʀɪᴍᴇ</a>\n"
            "‣ ᴜᴘᴅᴀᴛᴇꜱ ᴄʜᴀɴɴᴇʟ : <a href='https://t.me/PrimeXBots'>ᴘʀɪᴍᴇXʙᴏᴛꜱ</a>\n"
            "‣ ᴍᴀɪɴ ᴄʜᴀɴɴᴇʟ : <a href='https://t.me/PrimeCineZone'>ᴘʀɪᴍᴇ ᴄɪɴᴇᴢᴏɴᴇ</a>\n"
            "‣ ꜱᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ : <a href='https://t.me/Prime_Support_group'>ᴘʀɪᴍᴇX ꜱᴜᴘᴘᴏʀᴛ</a>\n"
            "‣ ᴅᴀᴛᴀʙᴀꜱᴇ : <a href='https://www.mongodb.com/'>ᴍᴏɴɢᴏᴅʙ</a>\n"
            "‣ ʙᴏᴛ ꜱᴇʀᴠᴇʀ : <a href='https://render.com'>ʀᴇɴᴅᴇʀ</a>\n"
            "‣ ʙᴜɪʟᴅ ꜱᴛᴀᴛᴜꜱ : v2.7.1 [ꜱᴛᴀʙʟᴇ]\n"
        )
        btns = [[InlineKeyboardButton("🧑‍💻 ꜱᴏᴜʀᴄᴇ ᴄoᴅᴇ 🧑‍💻", callback_data="source_prime")], [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="back_home")]]
        await query.message.edit_text(about_text, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(btns))

    elif data == "source_prime":
        await query.message.delete()
        await client.send_photo(chat_id=u_id, photo="https://i.postimg.cc/hvFZ93Ct/file-000000004188623081269b2440872960.png",
            caption=small_caps("hello dear, this is a private project. contact creator for source."),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("♚ ᴀᴅᴍɪɴ ♚", url="https://t.me/Prime_Admin_Support_ProBot")], [InlineKeyboardButton("• ᴄʟᴏsᴇ •", callback_data="closes")]]))

    elif data == "back_home":
        await query.message.delete()
        await start_handler(client, query.message)

    elif data == "closes": await query.message.delete()

    elif data == "h_t":
        u = await get_user(u_id)
        if not u["t_history"]: return await query.answer("Empty!", show_alert=True)
        btns = [[InlineKeyboardButton(f"🖼 ᴛʜᴜᴍʙ {i+1}", callback_data=f"vt_{i}"), InlineKeyboardButton("🗑", callback_data=f"dt_{i}")] for i in range(len(u["t_history"]))]
        await query.message.edit_text("Your Recent Thumbnails:", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("dt_"):
        idx = int(data.split("_")[1]); u = await get_user(u_id)
        u["t_history"].pop(idx)
        await users_col.update_one({"_id": u_id}, {"$set": {"t_history": u["t_history"]}})
        await query.answer("Deleted!", show_alert=True); await query.message.delete()

    elif data == "h_v":
        u = await get_user(u_id)
        if not u["v_history"]: return await query.answer("Empty!", show_alert=True)
        btns = [[InlineKeyboardButton(f"📹 ᴠɪᴅᴇᴏ {i+1}", callback_data=f"vv_{i}"), InlineKeyboardButton("🗑", callback_data=f"dv_{i}")] for i in range(len(u["v_history"]))]
        await query.message.edit_text("Your Recent Videos:", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("dv_"):
        idx = int(data.split("_")[1]); u = await get_user(u_id)
        u["v_history"].pop(idx)
        await users_col.update_one({"_id": u_id}, {"$set": {"v_history": u["v_history"]}})
        await query.answer("Deleted!", show_alert=True); await query.message.delete()

# --- SERVER ---
async def web_server():
    app_web = web.Application()
    app_web.router.add_get("/", lambda r: web.Response(text="PrimeSnapThumb Combined Active"))
    runner = web.AppRunner(app_web); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()

async def pinger():
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("http://0.0.0.0:8080"): pass
        except: pass
        await asyncio.sleep(600)

async def main():
    await web_server()
    asyncio.create_task(pinger())
    await app.start()
    print("🚀 Prime Combined Bot Started!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    loop.run_until_complete(main())
