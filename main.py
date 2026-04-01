import asyncio
import os

# পাইগ্রাম ইমপোর্ট করার আগেই একটি ইভেন্ট লুপ সেট করে দেওয়া
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# এবার পাইগ্রাম ইমপোর্ট করুন
from pyrogram import Client, filters, enums, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant
from motor.motor_asyncio import AsyncIOMotorClient
from aiohttp import web

# --- বাকি কনফিগারেশন আগের মতোই থাকবে ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "your_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_token")
MONGO_URL = os.environ.get("MONGO_URL", "your_mongodb_url")
AUTH_CHANNELS = [int(ch) for ch in os.environ.get("AUTH_CHANNEL", "").split() if ch.startswith("-100")]

app = Client("PrimeInstantBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- আপনার আগের সব ফাংশন (get_user, is_subscribed, etc.) এখানে থাকবে ---



db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["PrimeXBots_Thumb"]
users_col = db["users"]

#app = Client("PrimeInstantBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- UTILS & DB FUNCTIONS ---
async def get_user(user_id):
    user = await users_col.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "caption": "{filename}", "thumb": None, "t_history": [], "v_history": []}
        await users_col.insert_one(user)
    return user

async def is_subscribed(client, user_id):
    if not AUTH_CHANNELS:
        return True
    for chat_id in AUTH_CHANNELS:
        try:
            await client.get_chat_member(chat_id, user_id)
        except UserNotParticipant:
            return False
        except Exception:
            continue
    return True

async def get_fsub_buttons(client):
    buttons = []
    for chat_id in AUTH_CHANNELS:
        try:
            chat = await client.get_chat(chat_id)
            buttons.append([InlineKeyboardButton(f"✇ Join {chat.title} ✇", url=chat.invite_link)])
        except: continue
    buttons.append([InlineKeyboardButton("♻️ Refresh ♻️", callback_data="refresh_sub")])
    return InlineKeyboardMarkup(buttons)

# --- START MENU ---
def get_start_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("How to Use ❓", callback_data="help_ui")],
        [InlineKeyboardButton("Help 💡", callback_data="help_ui"), InlineKeyboardButton("About ℹ️", callback_data="about_ui")],
        [InlineKeyboardButton("Update Channel 📢", url="https://t.me/PrimeXBots"), InlineKeyboardButton("Support Group 👥", url="https://t.me/PrimeXBots")],
        [InlineKeyboardButton("Creator 👨‍💻", url="https://t.me/PrimeXBots")]
    ])

@app.on_message(filters.command("start"))
async def start_handler(client, message):
    user_id = message.from_user.id
    if not await is_subscribed(client, user_id):
        return await message.reply_photo(
            photo="https://i.postimg.cc/xdkd1h4m/IMG-20250715-153124-952.jpg",
            caption=f"👋 Hello {message.from_user.mention},\n\nYou must join our updates channel to use me. After joining, click the Refresh button.",
            reply_markup=await get_fsub_buttons(client)
        )
    
    await get_user(user_id)
    await message.reply_photo(
        photo="https://i.postimg.cc/xdkd1h4m/IMG-20250715-153124-952.jpg",
        caption=f"**Welcome to Instant Thumbnail Changer!**\n\nInstantly update video thumbnails and captions without any downloading. Powered by @PrimeXBots.",
        reply_markup=get_start_buttons()
    )

# --- CAPTION & THUMBNAIL ---
@app.on_message(filters.command("set_caption"))
async def set_cap(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/set_caption My Name {filename} @PrimeXBots`")
    new_cap = message.text.split(None, 1)[1]
    await users_col.update_one({"_id": message.from_user.id}, {"$set": {"caption": new_cap}})
    await message.reply_text(f"✅ **Caption set to:**\n`{new_cap}`")

@app.on_message(filters.photo)
async def save_thumb(client, message):
    file_id = message.photo.file_id
    user = await get_user(message.from_user.id)
    history = user.get("t_history", [])
    history.insert(0, file_id)
    await users_col.update_one({"_id": message.from_user.id}, {"$set": {"thumb": file_id, "t_history": history[:10]}})
    await message.reply_text("✅ **Thumbnail saved instantly!**")

# --- VIDEO HANDLER ---
@app.on_message(filters.video | filters.document)
async def video_handler(client, message):
    user = await get_user(message.from_user.id)
    if not user["thumb"]:
        return await message.reply_text("❌ Send a photo first!")
    
    status = await message.reply_text("⚡ Processing...")
    file_obj = message.video or message.document
    f_name = getattr(file_obj, 'file_name', 'video.mp4')
    caption = user["caption"].replace("{filename}", f_name)
    
    # Instant re-send using file_id and thumb
    await client.send_video(
        chat_id=message.chat.id,
        video=file_obj.file_id,
        thumb=await client.download_media(user["thumb"]),
        caption=caption,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Permanent Rename?", url="https://t.me/Prime_Fast_Renamer_Bot")]])
    )
    # History Update
    v_hist = user.get("v_history", [])
    v_hist.insert(0, file_obj.file_id)
    await users_col.update_one({"_id": message.from_user.id}, {"$set": {"v_history": v_hist[:10]}})
    await status.delete()

# --- HISTORY ---
@app.on_message(filters.command("history"))
async def hist_cmd(client, message):
    btns = [[InlineKeyboardButton("Show Thumbnails 🖼", callback_data="h_t"), InlineKeyboardButton("Show Videos 📹", callback_data="h_v")]]
    await message.reply_text("Check your recent history (Last 10 items):", reply_markup=InlineKeyboardMarkup(btns))

# --- CALLBACKS ---
@app.on_callback_query()
async def cb_logic(client, query: CallbackQuery):
    u_id = query.from_user.id
    data = query.data

    if data == "refresh_sub":
        if await is_subscribed(client, u_id):
            await query.answer("Thank you for joining! You can use the bot now.", show_alert=True)
            await query.message.delete()
            # Redirect to start
            await start_handler(client, query.message)
        else:
            await query.answer("⚠️ Warning: You haven't joined yet! Please join all channels.", show_alert=True)

    elif data == "help_ui":
        help_text = (
            "**How to Use:**\n"
            "1. Send a photo to set as thumbnail.\n"
            "2. Set custom caption with `/set_caption {filename} @PrimeXBots`.\n"
            "3. Send your video for instant processing.\n\n"
            "For permanent rename and blur, use: ||@Prime_Fast_Renamer_Bot||"
        )
        await query.message.edit_caption(caption=help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_home")]]))

    elif data == "about_ui":
        about_text = "This bot is a premium tool by @PrimeXBots to manage thumbnails instantly."
        btns = [[InlineKeyboardButton("Source Code 🔗", callback_data="source_prime")], [InlineKeyboardButton("Back", callback_data="back_home")]]
        await query.message.edit_caption(caption=about_text, reply_markup=InlineKeyboardMarkup(btns))

    elif data == "source_prime":
        await query.message.delete()
        await client.send_photo(
            chat_id=query.message.chat.id,
            photo="https://i.postimg.cc/hvFZ93Ct/file-000000004188623081269b2440872960.png",
            caption=(
                f"👋 Hello Dear 👋,\n\n"
                "⚠️ **THIS BOT IS A PRIVATE SOURCE PROJECT**\n\n"
                "This bot has latest and advanced features⚡️\n"
                "▸ If you want source code or like this bot contact me..!\n"
                "▸ I will create a bot for you or source code\n"
                "⇒ Contact Me - ♚ ADMIN ♚"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("♚ ADMIN ♚", url="https://t.me/Prime_Admin_Support_ProBot")],
                [InlineKeyboardButton("• CLOSE •", callback_data="closes")]
            ])
        )

    elif data == "back_home":
        await query.message.delete()
        await start_handler(client, query.message)

    elif data == "closes":
        await query.message.delete()

    elif data == "h_t":
        u = await get_user(u_id)
        if not u["t_history"]: return await query.answer("Empty!", show_alert=True)
        btns = [[InlineKeyboardButton(f"Thumbnail {i+1}", callback_data=f"v_t_{i}")] for i in range(len(u["t_history"]))]
        await query.message.edit_text("Recent Thumbnails:", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("v_t_"):
        idx = int(data.split("_")[2])
        u = await get_user(u_id)
        await client.send_photo(u_id, photo=u["t_history"][idx], caption="Your previous thumbnail.")

    elif data == "h_v":
        u = await get_user(u_id)
        if not u["v_history"]: return await query.answer("Empty!", show_alert=True)
        btns = [[InlineKeyboardButton(f"Video {i+1}", callback_data=f"v_v_{i}")] for i in range(len(u["v_history"]))]
        await query.message.edit_text("Recent Videos:", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("v_v_"):
        idx = int(data.split("_")[2])
        u = await get_user(u_id)
        await client.send_video(u_id, video=u["v_history"][idx], caption="Your previous video.")

# --- ওয়েব সার্ভার ও মেইন স্টার্টআপ ---
async def web_server():
    async def handle(request):
        return web.Response(text="Prime SnapThumb Bot is Online! Powered by @PrimeXBots")
    
    app_web = web.Application()
    app_web.router.add_get("/", handle)
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

async def main():
    # ওয়েব সার্ভার চালু
    await web_server()
    # বট চালু
    await app.start()
    print("🚀 Prime SnapThumb Bot Started Successfully!")
    # বটকে সচল রাখা
    await idle()
    # বন্ধ করার সময়
    await app.stop()

if __name__ == "__main__":
    # সরাসরি মেইন ফাংশন রান করা
    asyncio.get_event_loop().run_until_complete(main())
    
