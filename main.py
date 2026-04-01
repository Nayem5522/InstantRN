import os
import asyncio
import re
import time
import aiohttp
from pyrogram import Client, filters, enums, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant
from motor.motor_asyncio import AsyncIOMotorClient
from aiohttp import web

# --- FONT HELPER ---
def small_caps(text):
    mapping = {"a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ", "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ", "s": "s", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "ʏ", "z": "ᴢ"}
    return "".join(mapping.get(c.lower(), c) for c in text)

# --- CONFIG ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "your_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_token")
MONGO_URL = os.environ.get("MONGO_URL", "your_mongo_url")
AUTH_CHANNELS = [int(ch) for ch in os.environ.get("AUTH_CHANNEL", "").split() if ch.startswith("-100")]

app = Client("PrimeSnapThumb", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["PrimeXBots"]
users_col = db["users"]

# --- UTILS ---
async def get_user(user_id):
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "caption": "{filename}", "thumb": None, "t_history": [], "v_history": []}
        await users_col.insert_one(user)
    return user

async def is_subscribed(client, user_id):
    for chat_id in AUTH_CHANNELS:
        try:
            await client.get_chat_member(chat_id, user_id)
        except UserNotParticipant: return False
        except: continue
    return True

# --- START UI ---
def get_start_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(small_caps("〆 help 〆"), callback_data="help_ui"), InlineKeyboardButton(small_caps("〆 about 〆"), callback_data="about_ui")],
        [InlineKeyboardButton(small_caps("〄 updates channel 〄"), url="https://t.me/PrimeXBots"), InlineKeyboardButton(small_caps("✪ support group ✪"), url="https://t.me/Prime_Support_group")],
        [InlineKeyboardButton(small_caps("✧ creator ✧"), url="https://t.me/Prime_Nayem")]
    ])

@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    if not await is_subscribed(client, user_id):
        buttons = []
        for chat_id in AUTH_CHANNELS:
            chat = await client.get_chat(chat_id)
            buttons.append([InlineKeyboardButton(f"✇ ᴊᴏɪɴ {chat.title} ✇", url=chat.invite_link)])
        buttons.append([InlineKeyboardButton(small_caps("♻️ refresh ♻️"), callback_data="refresh_sub")])
        return await message.reply_photo(photo="https://i.postimg.cc/xdkd1h4m/IMG-20250715-153124-952.jpg", caption=small_caps(f"👋 hello {message.from_user.first_name},\n\nɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴜꜱᴇ ᴍᴇ, ʏᴏᴜ ᴍᴜꜱᴛ ꜰɪʀꜱᴛ ᴊᴏɪɴ ᴏᴜʀ ᴜᴘᴅᴀᴛᴇꜱ ᴄʜᴀɴɴᴇʟ."), reply_markup=InlineKeyboardMarkup(buttons))

    await get_user(user_id)
    await message.reply_photo(photo="https://i.postimg.cc/xdkd1h4m/IMG-20250715-153124-952.jpg", caption=small_caps("welcome to prime snapthumb bot! instantly update video thumbnails and captions."), reply_markup=get_start_buttons())

# --- SET CAPTION & THUMB ---
@app.on_message(filters.command("set_caption"))
async def set_cap(client, message):
    if len(message.command) < 2: return await message.reply_text(small_caps("usage: /set_caption {filename} @PrimeXBots"))
    new_cap = message.text.split(None, 1)[1]
    await users_col.update_one({"_id": message.from_user.id}, {"$set": {"caption": new_cap}})
    await message.reply_text(small_caps(f"✅ caption saved: {new_cap}"))

@app.on_message(filters.photo)
async def thumb_save(client, message):
    file_id = message.photo.file_id
    user = await get_user(message.from_user.id)
    history = user.get("t_history", [])
    history.insert(0, file_id)
    await users_col.update_one({"_id": message.from_user.id}, {"$set": {"thumb": file_id, "t_history": history[:10]}})
    await message.reply_text(small_caps("✅ thumbnail saved instantly!"))

# --- VIDEO PROCESSING ---
@app.on_message(filters.video | filters.document)
async def process_video(client, message):
    user = await get_user(message.from_user.id)
    if not user["thumb"]: return await message.reply_text(small_caps("❌ please send a photo first!"))

    # Processing Sticker
    sticker = await message.reply_sticker("CAACAgUAAxkBAAKGfGnNPmV4Bwsx_0W1Qk8h6p3Q423nAALbEAACdYaYVO2S9fNnW52THgQ")
    await asyncio.sleep(4) # 4 second delay
    await sticker.delete()

    file_obj = message.video or message.document
    # Clean File Name Logic
    raw_name = getattr(file_obj, 'file_name', 'video.mp4')
    clean_name = raw_name.replace("_", " ").replace(".", " ").replace("mp4", "").replace("mkv", "").strip()
    
    final_caption = user["caption"].replace("{filename}", clean_name)
    thumb_path = await client.download_media(user["thumb"])

    try:
        # We use re-upload for instant thumbnail change effect (Streaming style)
        await client.send_video(
            chat_id=message.chat.id,
            video=file_obj.file_id,
            thumb=thumb_path,
            caption=small_caps(final_caption),
            supports_streaming=True
        )
        # Update History
        v_hist = user.get("v_history", [])
        v_hist.insert(0, file_obj.file_id)
        await users_col.update_one({"_id": message.from_user.id}, {"$set": {"v_history": v_hist[:10]}})
    except Exception as e:
        await message.reply_text(f"Error: {e}")
    finally:
        if os.path.exists(thumb_path): os.remove(thumb_path)

# --- HISTORY ---
@app.on_message(filters.command("history"))
async def history(client, message):
    btns = [[InlineKeyboardButton(small_caps("show thumbnails 🖼"), callback_data="h_t"), InlineKeyboardButton(small_caps("show videos 📹"), callback_data="h_v")]]
    await message.reply_text(small_caps("your recent history (last 10):"), reply_markup=InlineKeyboardMarkup(btns))

# --- CALLBACK HANDLER ---
@app.on_callback_query()
async def cb_handler(client, query: CallbackQuery):
    u_id = query.from_user.id
    data = query.data
    me = await client.get_me()

    if data == "refresh_sub":
        if await is_subscribed(client, u_id):
            await query.answer(small_caps("thank you for joining!"), show_alert=True)
            await query.message.delete()
            await start(client, query.message)
        else: await query.answer(small_caps("⚠️ you haven't joined all channels!"), show_alert=True)

    elif data == "help_ui":
        help_text = small_caps("1. send a photo to set as thumb.\n2. set caption with /set_caption.\n3. send video.\n\nfor permanent rename use: ||@Prime_Fast_Renamer_Bot||")
        await query.message.edit_caption(caption=help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(small_caps("🔙 back"), callback_data="back_home")]]))

    elif data == "about_ui":
        about_text = (
            f"<b><blockquote>⍟───[ <a href='https://t.me/PrimeXBots'>ᴍʏ ᴅᴇᴛᴀɪʟꜱ ʙʏ ᴘʀɪᴍᴇXʙᴏᴛꜱ</a> ]───⍟</blockquote></b>\n\n"
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
        btns = [[InlineKeyboardButton(small_caps("🧑‍💻 source code 🧑‍💻"), callback_data="source_prime")], [InlineKeyboardButton(small_caps("🔙 back"), callback_data="back_home")]]
        await query.message.edit_text(about_text, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(btns))

    elif data == "source_prime":
        await query.message.delete()
        await client.send_photo(chat_id=u_id, photo="https://i.postimg.cc/hvFZ93Ct/file-000000004188623081269b2440872960.png", 
            caption=small_caps("👋 hello dear, this is a private source project. contact creator for source code."),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(small_caps("♚ admin ♚"), url="https://t.me/Prime_Admin_Support_ProBot")], [InlineKeyboardButton(small_caps("• close •"), callback_data="closes")]]))

    elif data == "back_home":
        await query.message.delete()
        await start(client, query.message)

    elif data == "closes": await query.message.delete()

    elif data == "h_t":
        u = await get_user(u_id)
        if not u["t_history"]: return await query.answer("empty!", show_alert=True)
        btns = [[InlineKeyboardButton(f"🖼 ᴛʜᴜᴍʙ {i+1}", callback_data=f"vt_{i}"), InlineKeyboardButton("🗑", callback_data=f"dt_{i}")] for i in range(len(u["t_history"]))]
        await query.message.edit_text(small_caps("recent thumbnails:"), reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("vt_"):
        idx = int(data.split("_")[1]); u = await get_user(u_id)
        await client.send_photo(u_id, photo=u["t_history"][idx], caption=small_caps("here is your thumb."))

    elif data.startswith("dt_"): # Delete Thumb from history
        idx = int(data.split("_")[1]); u = await get_user(u_id)
        u["t_history"].pop(idx)
        await users_col.update_one({"_id": u_id}, {"$set": {"t_history": u["t_history"]}})
        await query.answer(small_caps("deleted!"), show_alert=True)
        await query.message.delete()

    elif data == "h_v":
        u = await get_user(u_id)
        if not u["v_history"]: return await query.answer("empty!", show_alert=True)
        btns = [[InlineKeyboardButton(f"📹 ᴠɪᴅᴇᴏ {i+1}", callback_data=f"vv_{i}"), InlineKeyboardButton("🗑", callback_data=f"dv_{i}")] for i in range(len(u["v_history"]))]
        await query.message.edit_text(small_caps("recent videos:"), reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("vv_"):
        idx = int(data.split("_")[1]); u = await get_user(u_id)
        await client.send_video(u_id, video=u["v_history"][idx], caption=small_caps("here is your video."))

    elif data.startswith("dv_"): # Delete Video from history
        idx = int(data.split("_")[1]); u = await get_user(u_id)
        u["v_history"].pop(idx)
        await users_col.update_one({"_id": u_id}, {"$set": {"v_history": u["v_history"]}})
        await query.answer(small_caps("deleted!"), show_alert=True)
        await query.message.delete()

# --- SERVER & PINGER ---
async def web_server():
    app_web = web.Application()
    app_web.router.add_get("/", lambda r: web.Response(text="PrimeSnapThumb is Active"))
    runner = web.AppRunner(app_web); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()

async def pinger():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://0.0.0.0:8080") as resp: pass
        except: pass
        await asyncio.sleep(600) # Ping every 10 mins

async def main():
    await web_server()
    asyncio.create_task(pinger())
    await app.start()
    print("🚀 Prime SnapThumb Online!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
    
