#!/usr/bin/env python3
# ================================================================
# ANICITY RASMIY BOT - TO'LIQ TUZATILGAN VERSIYA
# ================================================================
# Muallif: @s_2akk
# Kanal: @AniCity_Rasmiy
# Version: 3.0 FINAL
# ================================================================

import asyncio
import logging
import os
import re
import io
import sys
import json
from datetime import datetime
from typing import Tuple, List, Dict, Any, Optional
from contextlib import asynccontextmanager

# Kutubxonalarni tekshirish va import qilish
try:
    from dotenv import load_dotenv
    import aiosqlite
    import aiohttp
    from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
    from aiogram.filters import Command
    from aiogram.types import (
        Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
        ReplyKeyboardMarkup, KeyboardButton, FSInputFile, BufferedInputFile
    )
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import StatesGroup, State
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.utils.keyboard import InlineKeyboardBuilder
except ImportError as e:
    print(f"❌ Kutubxona import xatosi: {e}")
    print("Iltimos, quyidagi buyruq bilan kutubxonalarni o'rnating:")
    print("pip install aiogram aiosqlite python-dotenv aiohttp")
    sys.exit(1)

# ================= KONFIGURATSIYA =================
try:
    load_dotenv()
except Exception as e:
    print(f"⚠️ .env fayl yuklash xatosi: {e}")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = "8545654766:AAHc9XBWMsgQWxibBXcPN44vu1rZ6AILlMg"
    print("⚠️ BOT_TOKEN default qiymat ishlatilmoqda")

ADMINS_STR = os.getenv("ADMINS", "5675087151,6498527560")
ADMINS = [int(x.strip()) for x in ADMINS_STR.split(",") if x.strip().isdigit()]

MAIN_CHANNEL = os.getenv("MAIN_CHANNEL", "@AniCity_Rasmiy")
BASE_CHANNEL_ID_STR = os.getenv("BASE_CHANNEL_ID", "-1003888128587")
BASE_CHANNEL_ID = int(BASE_CHANNEL_ID_STR) if BASE_CHANNEL_ID_STR.lstrip('-').isdigit() else -1003888128587

AUTHOR_LINK = "https://t.me/S_2ak"
AUTHOR_USERNAME = "@s_2akk"

START_IMAGE_PATH = "Anime.jpg"
ADMIN_IMAGE_PATH = "admin.png"

# ================= LOGING =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= DATABASE (aiosqlite) =================
DB_NAME = 'anime_bot.db'

class Database:
    def __init__(self, db_path: str = DB_NAME):
        self.db_path = db_path
        self._conn = None
    
    async def connect(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._init_tables()
        logger.info("✅ Database ulandi!")
        return self._conn
    
    async def _init_tables(self):
        await self._conn.execute('''
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code INTEGER UNIQUE,
            type TEXT,
            name TEXT UNIQUE,
            description TEXT,
            image_url TEXT,
            genre TEXT,
            status TEXT DEFAULT "ongoing",
            season INTEGER DEFAULT 1,
            total_parts INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            voice TEXT DEFAULT "",
            sponsor TEXT DEFAULT "",
            quality TEXT DEFAULT "720p",
            created_at TEXT
        )
        ''')
        
        await self._conn.execute('''
        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id INTEGER,
            part_number INTEGER,
            file_id TEXT,
            caption TEXT,
            created_at TEXT,
            FOREIGN KEY (media_id) REFERENCES media (id) ON DELETE CASCADE
        )
        ''')
        
        await self._conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_blocked INTEGER DEFAULT 0,
            registered_at TEXT,
            last_active TEXT
        )
        ''')
        
        await self._conn.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at TEXT
        )
        ''')
        
        await self._conn.execute('''
        CREATE TABLE IF NOT EXISTS forced_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_username TEXT UNIQUE,
            channel_id INTEGER,
            is_active INTEGER DEFAULT 1,
            added_at TEXT
        )
        ''')
        
        now = datetime.now().isoformat()
        for admin_id in ADMINS:
            await self._conn.execute(
                "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
                (admin_id, admin_id, now)
            )
        
        await self._conn.commit()
        logger.info("✅ Jadvallar yaratildi!")
    
    @asynccontextmanager
    async def execute(self, query: str, params: tuple = ()):
        async with self._conn.execute(query, params) as cursor:
            yield cursor
    
    async def fetch_one(self, query: str, params: tuple = ()):
        try:
            async with self._conn.execute(query, params) as cursor:
                return await cursor.fetchone()
        except Exception as e:
            logger.error(f"fetch_one xatosi: {e}")
            return None
    
    async def fetch_all(self, query: str, params: tuple = ()):
        try:
            async with self._conn.execute(query, params) as cursor:
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f"fetch_all xatosi: {e}")
            return []
    
    async def execute_and_commit(self, query: str, params: tuple = ()):
        try:
            await self._conn.execute(query, params)
            await self._conn.commit()
            return True
        except Exception as e:
            logger.error(f"execute_and_commit xatosi: {e}")
            await self._conn.rollback()
            return False
    
    async def close(self):
        if self._conn:
            await self._conn.close()

db = Database()

# ================= BOT =================
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ================= YORDAMCHI FUNKSIYALAR =================
def get_start_image() -> Optional[FSInputFile]:
    try:
        return FSInputFile(START_IMAGE_PATH) if os.path.exists(START_IMAGE_PATH) else None
    except Exception as e:
        logger.error(f"Rasm xatosi: {e}")
        return None

def get_admin_image() -> Optional[FSInputFile]:
    try:
        return FSInputFile(ADMIN_IMAGE_PATH) if os.path.exists(ADMIN_IMAGE_PATH) else None
    except Exception as e:
        logger.error(f"Admin rasm xatosi: {e}")
        return None

def get_welcome_text() -> str:
    return f"""🎬 <b>AniCity Rasmiy Bot</b> 🎬

✨ <b>Botimizga xush kelibsiz!</b> ✨

📚 <b>Bot imkoniyatlari:</b>
🔍 Kod orqali qidiruv
🎬 Anime va dramalarni nom bilan qidirish
🖼 Rasm orqali anime topish
📺 Barcha qismlarni tomosha qilish

📢 <b>Asosiy kanal:</b> {MAIN_CHANNEL}
👨‍💻 <b>Muallif:</b> <a href='{AUTHOR_LINK}'>{AUTHOR_USERNAME}</a>
🆘 <b>Yordam:</b> <a href='{AUTHOR_LINK}'>{AUTHOR_USERNAME}</a>

⬇️ <b>Quyidagi tugmalardan birini tanlang:</b> ⬇️"""

def start_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Kod orqali qidiruv", callback_data="search_by_code")],
        [InlineKeyboardButton(text="🎬 Anime Qidiruv", callback_data="search_anime"),
         InlineKeyboardButton(text="🎭 Drama Qidiruv", callback_data="search_drama")],
        [InlineKeyboardButton(text="🖼 Rasm Orqali Anime Qidiruv", callback_data="search_image"),
         InlineKeyboardButton(text="📖 Qo'llanma", callback_data="guide")],
        [InlineKeyboardButton(text="📢 Reklama", callback_data="advertisement"),
         InlineKeyboardButton(text="📋 Ro'yxat", callback_data="list_all")],
        [InlineKeyboardButton(text="🔐 Admin Panel", callback_data="admin_panel")]
    ])

def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Media Qo'shish"), KeyboardButton(text="➕ Qism Qo'shish")],
        [KeyboardButton(text="➕ Ko'p Qism Qo'shish"), KeyboardButton(text="✏️ Media Tahrirlash")],
        [KeyboardButton(text="✏️ Qismni Tahrirlash"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="📢 Xabar Yuborish"), KeyboardButton(text="🔗 Majburiy A'zo")],
        [KeyboardButton(text="👑 Admin Qo'shish"), KeyboardButton(text="📨 Post Qilish")],
        [KeyboardButton(text="🎬 Qismni Post Qilish"), KeyboardButton(text="🔙 Asosiy menyu")]
    ], resize_keyboard=True)

async def is_admin(user_id: int) -> bool:
    try:
        result = await db.fetch_one("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        return result is not None or user_id in ADMINS
    except Exception as e:
        logger.error(f"is_admin xatosi: {e}")
        return user_id in ADMINS

async def is_owner(user_id: int) -> bool:
    return user_id in ADMINS

async def add_user(user) -> None:
    try:
        now = datetime.now().isoformat()
        await db.execute_and_commit(
            "INSERT OR IGNORE INTO users (id, username, first_name, last_name, registered_at, last_active) VALUES (?, ?, ?, ?, ?, ?)",
            (user.id, user.username or "", user.first_name or "", user.last_name or "", now, now)
        )
    except Exception as e:
        logger.error(f"add_user xatosi: {e}")

async def update_user_activity(user_id: int) -> None:
    try:
        await db.execute_and_commit(
            "UPDATE users SET last_active = ? WHERE id = ?",
            (datetime.now().isoformat(), user_id)
        )
    except Exception as e:
        logger.error(f"update_user_activity xatosi: {e}")

async def safe_send_message(chat_id: int, text: str, **kwargs):
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"Xabar xatosi {chat_id}: {e}")
        return None

async def safe_send_photo(chat_id: int, photo, caption=None, **kwargs):
    try:
        return await bot.send_photo(chat_id, photo, caption=caption, **kwargs)
    except Exception as e:
        logger.error(f"Rasm xatosi {chat_id}: {e}")
        if caption:
            return await safe_send_message(chat_id, caption, **kwargs)
        return None

async def safe_send_video(chat_id: int, video, caption=None, **kwargs):
    try:
        return await bot.send_video(chat_id, video, caption=caption, **kwargs)
    except Exception as e:
        logger.error(f"Video xatosi {chat_id}: {e}")
        return None

# ================= MAJBURIY OBUNA =================
async def check_subscription(user_id: int) -> Tuple[bool, List[dict]]:
    try:
        rows = await db.fetch_all("SELECT id, channel_username, channel_id FROM forced_channels WHERE is_active = 1")
        channels = list(rows) if rows else []
        
        if not channels:
            return True, []
        
        not_subscribed = []
        for ch in channels:
            ch_id = ch[0] if isinstance(ch, tuple) else ch['id']
            channel_username = ch[1] if isinstance(ch, tuple) else ch['channel_username']
            channel_id_db = ch[2] if isinstance(ch, tuple) else ch['channel_id']
            
            clean_username = channel_username.replace('@', '').strip()
            if not clean_username:
                continue
            
            try:
                if not channel_id_db:
                    try:
                        chat = await bot.get_chat(f"@{clean_username}")
                        channel_id_db = chat.id
                        await db.execute_and_commit(
                            "UPDATE forced_channels SET channel_id = ? WHERE id = ?",
                            (channel_id_db, ch_id)
                        )
                    except Exception as e:
                        logger.warning(f"Kanal topilmadi {clean_username}: {e}")
                        continue
                
                try:
                    member = await bot.get_chat_member(chat_id=channel_id_db, user_id=user_id)
                    if member.status in ['left', 'kicked']:
                        not_subscribed.append({
                            'id': ch_id,
                            'username': f"@{clean_username}",
                            'invite_link': None
                        })
                except Exception as e:
                    logger.warning(f"A'zolik tekshirib bo'lmadi {clean_username}: {e}")
                    
            except Exception as e:
                logger.error(f"Kanal tekshirish xatosi {channel_username}: {e}")
        
        return len(not_subscribed) == 0, not_subscribed
    except Exception as e:
        logger.error(f"check_subscription xatosi: {e}")
        return True, []

async def get_subscription_keyboard(not_subscribed: List[dict]) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for ch in not_subscribed:
        username = ch['username']
        clean = username.replace('@', '')
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"📢 {username}", url=f"https://t.me/{clean}")
        ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="✅ A'zolikni tekshirish", callback_data="check_subscription")
    ])
    return keyboard

# ================= MIDDLEWARE =================
class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user_id = None
        is_callback = False
        
        if isinstance(event, Message):
            user_id = event.from_user.id
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            is_callback = True
            if event.data == "check_subscription":
                return await handler(event, data)
        
        if not user_id:
            return await handler(event, data)
        
        try:
            subscribed, not_subscribed = await check_subscription(user_id)
            if not subscribed:
                text = "❌ <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>\n\n"
                for ch in not_subscribed:
                    text += f"• {ch['username']}\n"
                text += "\n✅ A'zo bo'lgandan so'ng <b>Tekshirish</b> tugmasini bosing."
                keyboard = await get_subscription_keyboard(not_subscribed)
                
                if is_callback:
                    try:
                        await event.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
                    except:
                        await event.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
                else:
                    await event.answer(text, reply_markup=keyboard, parse_mode="HTML")
                return
        except Exception as e:
            logger.error(f"Middleware xatosi: {e}")
        
        return await handler(event, data)

dp.message.middleware(SubscriptionMiddleware())
dp.callback_query.middleware(SubscriptionMiddleware())

# ================= STATE'LAR =================
class ForcedChannelState(StatesGroup):
    waiting_for_channel = State()

class AddMediaState(StatesGroup):
    type = State()
    name = State()
    code = State()
    description = State()
    image = State()
    genre = State()
    status = State()
    season = State()
    voice = State()
    sponsor = State()
    quality = State()

class AddPartState(StatesGroup):
    select_media = State()
    part_number = State()
    video = State()
    caption = State()

class AddMultiplePartsState(StatesGroup):
    select_media = State()
    videos = State()

class EditMediaState(StatesGroup):
    select = State()
    field = State()
    value = State()

class EditPartState(StatesGroup):
    select_media = State()
    select_part = State()
    field = State()
    value = State()

class BroadcastState(StatesGroup):
    message = State()

class AdminManageState(StatesGroup):
    action = State()
    user_id = State()

class SearchState(StatesGroup):
    query = State()
    search_type = State()

class PostState(StatesGroup):
    media_id = State()
    channel = State()
    confirm = State()

class PartPostState(StatesGroup):
    media_id = State()
    part_id = State()
    channel = State()
    confirm = State()

class CodeSearchState(StatesGroup):
    waiting_for_code = State()

class ImageSearchState(StatesGroup):
    waiting_for_image = State()

# ================= START HANDLER =================
@dp.message(Command("start"))
async def start(message: Message):
    try:
        await add_user(message.from_user)
        await update_user_activity(message.from_user.id)
        
        args = message.text.split()
        if len(args) > 1 and args[1].startswith("code_"):
            code_part = args[1].replace("code_", "")
            if "&part=" in code_part:
                code_str, part_num_str = code_part.split("&part=")
                try:
                    code_int = int(code_str)
                    part_num_int = int(part_num_str)
                    media_row = await db.fetch_one("SELECT id FROM media WHERE code = ?", (code_int,))
                    if media_row:
                        media_id = media_row[0] if isinstance(media_row, tuple) else media_row['id']
                        part_row = await db.fetch_one(
                            "SELECT file_id, caption FROM parts WHERE media_id = ? AND part_number = ?",
                            (media_id, part_num_int)
                        )
                        if part_row:
                            file_id = part_row[0] if isinstance(part_row, tuple) else part_row['file_id']
                            caption = part_row[1] if isinstance(part_row, tuple) else part_row['caption']
                            media_name_row = await db.fetch_one("SELECT name FROM media WHERE id = ?", (media_id,))
                            media_name = media_name_row[0] if media_name_row else "Anime"
                            full_caption = f"🎬 {media_name}\n📹 {part_num_int}-qism\n\n{caption if caption else ''}"
                            await safe_send_video(message.chat.id, video=file_id, caption=full_caption, parse_mode="HTML")
                            return
                except Exception as e:
                    logger.error(f"Deep link xatosi: {e}")
        
        start_image = get_start_image()
        welcome_text = get_welcome_text()
        
        if start_image:
            await safe_send_photo(message.chat.id, photo=start_image, caption=welcome_text, reply_markup=start_menu(), parse_mode="HTML")
        else:
            await safe_send_message(message.chat.id, welcome_text, reply_markup=start_menu(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"start xatosi: {e}")
        await message.answer("❌ Xatolik yuz berdi!")

@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery):
    try:
        subscribed, not_subscribed = await check_subscription(callback.from_user.id)
        if subscribed:
            welcome_text = get_welcome_text()
            start_image = get_start_image()
            try:
                await callback.message.delete()
            except:
                pass
            if start_image:
                await safe_send_photo(callback.from_user.id, photo=start_image, caption=welcome_text, reply_markup=start_menu(), parse_mode="HTML")
            else:
                await safe_send_message(callback.from_user.id, welcome_text, reply_markup=start_menu(), parse_mode="HTML")
        else:
            text = "❌ <b>Siz hali ham quyidagi kanallarga a'zo emassiz:</b>\n\n"
            for ch in not_subscribed:
                text += f"• {ch['username']}\n"
            text += "\n✅ A'zo bo'lgandan so'ng <b>Tekshirish</b> tugmasini bosing."
            keyboard = await get_subscription_keyboard(not_subscribed)
            try:
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            except:
                await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"check_subscription_callback xatosi: {e}")
    await callback.answer()

@dp.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass
    welcome_text = get_welcome_text()
    start_image = get_start_image()
    if start_image:
        await safe_send_photo(callback.from_user.id, photo=start_image, caption=welcome_text, reply_markup=start_menu(), parse_mode="HTML")
    else:
        await safe_send_message(callback.from_user.id, welcome_text, reply_markup=start_menu(), parse_mode="HTML")
    await callback.answer()

@dp.message(F.text == "🔙 Asosiy menyu")
async def back_to_main_reply(message: Message):
    welcome_text = get_welcome_text()
    start_image = get_start_image()
    if start_image:
        await safe_send_photo(message.chat.id, photo=start_image, caption=welcome_text, reply_markup=start_menu(), parse_mode="HTML")
    else:
        await safe_send_message(message.chat.id, welcome_text, reply_markup=start_menu(), parse_mode="HTML")

# ================= ADMIN PANEL =================
@dp.callback_query(F.data == "admin_panel")
async def admin_panel_callback(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Siz admin emassiz!", show_alert=True)
        return
    
    users_row = await db.fetch_one("SELECT COUNT(*) FROM users WHERE is_blocked = 0")
    media_row = await db.fetch_one("SELECT COUNT(*) FROM media")
    parts_row = await db.fetch_one("SELECT COUNT(*) FROM parts")
    admins_row = await db.fetch_one("SELECT COUNT(*) FROM admins")
    
    users = users_row[0] if users_row else 0
    media = media_row[0] if media_row else 0
    parts = parts_row[0] if parts_row else 0
    admins = admins_row[0] if admins_row else 0
    
    admin_image = get_admin_image()
    admin_text = (
        "🔐 <b>Admin Panel</b> 🔐\n\n"
        f"👑 Adminlar: {admins}\n"
        f"🎬 Media: {media}\n"
        f"📹 Qismlar: {parts}\n"
        f"👥 Foydalanuvchilar: {users}\n\n"
        "⬇️ Quyidagi tugmalardan foydalaning:"
    )
    
    try:
        await callback.message.delete()
    except:
        pass
    
    if admin_image:
        await safe_send_photo(callback.from_user.id, photo=admin_image, caption=admin_text, reply_markup=admin_menu(), parse_mode="HTML")
    else:
        await safe_send_message(callback.from_user.id, admin_text, reply_markup=admin_menu(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "back_to_admin_reply")
async def back_to_admin_reply(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    
    users_row = await db.fetch_one("SELECT COUNT(*) FROM users WHERE is_blocked = 0")
    media_row = await db.fetch_one("SELECT COUNT(*) FROM media")
    parts_row = await db.fetch_one("SELECT COUNT(*) FROM parts")
    admins_row = await db.fetch_one("SELECT COUNT(*) FROM admins")
    
    users = users_row[0] if users_row else 0
    media = media_row[0] if media_row else 0
    parts = parts_row[0] if parts_row else 0
    admins = admins_row[0] if admins_row else 0
    
    admin_image = get_admin_image()
    admin_text = (
        "🔐 <b>Admin Panel</b> 🔐\n\n"
        f"👑 Adminlar: {admins}\n"
        f"🎬 Media: {media}\n"
        f"📹 Qismlar: {parts}\n"
        f"👥 Foydalanuvchilar: {users}\n\n"
        "⬇️ Quyidagi tugmalardan foydalaning:"
    )
    
    try:
        await callback.message.delete()
    except:
        pass
    
    if admin_image:
        await safe_send_photo(callback.from_user.id, photo=admin_image, caption=admin_text, reply_markup=admin_menu(), parse_mode="HTML")
    else:
        await safe_send_message(callback.from_user.id, admin_text, reply_markup=admin_menu(), parse_mode="HTML")
    await callback.answer()

# ================= MEDIA QO'SHISH =================
@dp.message(F.text == "➕ Media Qo'shish")
async def add_media_start(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Anime", callback_data="media_type_anime")],
        [InlineKeyboardButton(text="🎭 Drama", callback_data="media_type_drama")],
        [InlineKeyboardButton(text="🔙 Bekor", callback_data="back_to_admin_reply")]
    ])
    await message.answer("Media turini tanlang:", reply_markup=keyboard)
    await state.set_state(AddMediaState.type)

@dp.callback_query(AddMediaState.type, F.data.startswith("media_type_"))
async def add_media_type(callback: CallbackQuery, state: FSMContext):
    media_type = callback.data.split("_")[2]
    await state.update_data(type=media_type)
    try:
        await callback.message.edit_text("Media nomini kiriting:")
    except:
        await safe_send_message(callback.from_user.id, "Media nomini kiriting:")
    await state.set_state(AddMediaState.name)
    await callback.answer()

@dp.message(AddMediaState.name)
async def add_media_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Media kodini kiriting (faqat raqam, masalan: 1, 2, 3...):")
    await state.set_state(AddMediaState.code)

@dp.message(AddMediaState.code)
async def add_media_code(message: Message, state: FSMContext):
    try:
        code = int(message.text.strip())
        existing = await db.fetch_one("SELECT id FROM media WHERE code = ?", (code,))
        if existing:
            await message.answer(f"❌ '{code}' kodi mavjud! Boshqa kod kiriting:")
            return
        await state.update_data(code=code)
        await message.answer("Media tavsifini kiriting:")
        await state.set_state(AddMediaState.description)
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting!")

@dp.message(AddMediaState.description)
async def add_media_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Rasm yuboring (jpg/png) yoki URL kiriting:")
    await state.set_state(AddMediaState.image)

@dp.message(AddMediaState.image, F.photo)
async def add_media_image_photo(message: Message, state: FSMContext):
    await state.update_data(image=message.photo[-1].file_id)
    await message.answer("Janrlarini kiriting (vergul bilan):")
    await state.set_state(AddMediaState.genre)

@dp.message(AddMediaState.image, F.text)
async def add_media_image_url(message: Message, state: FSMContext):
    await state.update_data(image=message.text)
    await message.answer("Janrlarini kiriting (vergul bilan):")
    await state.set_state(AddMediaState.genre)

@dp.message(AddMediaState.genre)
async def add_media_genre(message: Message, state: FSMContext):
    await state.update_data(genre=message.text)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Davom etmoqda", callback_data="add_status_ongoing")],
        [InlineKeyboardButton(text="✅ Tugallangan", callback_data="add_status_completed")],
        [InlineKeyboardButton(text="⏸ To'xtatilgan", callback_data="add_status_hiatus")]
    ])
    await message.answer("Media holatini tanlang:", reply_markup=keyboard)
    await state.set_state(AddMediaState.status)

@dp.callback_query(AddMediaState.status, F.data.startswith("add_status_"))
async def add_media_status(callback: CallbackQuery, state: FSMContext):
    status = callback.data.split("_")[2]
    await state.update_data(status=status)
    try:
        await callback.message.edit_text("Sezon raqamini kiriting (masalan: 1):")
    except:
        await safe_send_message(callback.from_user.id, "Sezon raqamini kiriting (masalan: 1):")
    await state.set_state(AddMediaState.season)
    await callback.answer()

@dp.message(AddMediaState.season)
async def add_media_season(message: Message, state: FSMContext):
    try:
        season = int(message.text.strip())
        await state.update_data(season=season)
        await message.answer("Ovoz beruvchi(lar)ni kiriting (masalan: AniCity):")
        await state.set_state(AddMediaState.voice)
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting!")

@dp.message(AddMediaState.voice)
async def add_media_voice(message: Message, state: FSMContext):
    await state.update_data(voice=message.text)
    await message.answer("Himoy (homiy) ni kiriting (masalan: Nuqtacha):")
    await state.set_state(AddMediaState.sponsor)

@dp.message(AddMediaState.sponsor)
async def add_media_sponsor(message: Message, state: FSMContext):
    await state.update_data(sponsor=message.text)
    await message.answer("Sifatni kiriting (masalan: 720p):")
    await state.set_state(AddMediaState.quality)

@dp.message(AddMediaState.quality)
async def add_media_quality(message: Message, state: FSMContext):
    await state.update_data(quality=message.text)
    data = await state.get_data()
    success = await db.execute_and_commit(
        "INSERT INTO media (code, type, name, description, image_url, genre, status, season, voice, sponsor, quality, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (data['code'], data['type'], data['name'], data['description'], data['image'], data['genre'], data['status'], data['season'], data['voice'], data['sponsor'], data['quality'], datetime.now().isoformat())
    )
    if success:
        await message.answer(f"✅ <b>{data['name']}</b> qo'shildi!\n\n🔢 Kod: <code>{data['code']}</code>", parse_mode="HTML")
    else:
        await message.answer("❌ Xatolik yuz berdi!")
    await state.clear()

# ================= QISM QO'SHISH =================
@dp.message(F.text == "➕ Qism Qo'shish")
async def add_part_start(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("Qaysi animega qism qo'shmoqchisiz?\nAnime nomi yoki kodini kiriting:", parse_mode="HTML")
    await state.set_state(AddPartState.select_media)

@dp.message(AddPartState.select_media)
async def add_part_select_media(message: Message, state: FSMContext):
    query = message.text.strip()
    try:
        code = int(query)
        media_row = await db.fetch_one("SELECT id, name FROM media WHERE code = ?", (code,))
    except ValueError:
        media_row = await db.fetch_one("SELECT id, name FROM media WHERE name LIKE ?", (f"%{query}%",))
    
    if not media_row:
        await message.answer(f"❌ '{query}' bo'yicha media topilmadi! Qayta kiriting:")
        return
    
    media_id = media_row[0] if isinstance(media_row, tuple) else media_row['id']
    media_name = media_row[1] if isinstance(media_row, tuple) else media_row['name']
    await state.update_data(media_id=media_id)
    await message.answer(f"📺 <b>{media_name}</b> uchun qism raqamini kiriting:", parse_mode="HTML")
    await state.set_state(AddPartState.part_number)

@dp.message(AddPartState.part_number)
async def add_part_number(message: Message, state: FSMContext):
    try:
        part_num = int(message.text)
        data = await state.get_data()
        existing = await db.fetch_one("SELECT id FROM parts WHERE media_id = ? AND part_number = ?", (data['media_id'], part_num))
        if existing:
            await message.answer(f"⚠️ {part_num}-qism mavjud! Yangi raqam kiriting:")
            return
        await state.update_data(part_number=part_num)
        await message.answer(f"🎬 {part_num}-qism videosini yuboring:")
        await state.set_state(AddPartState.video)
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting!")

@dp.message(AddPartState.video, F.video)
async def add_part_video(message: Message, state: FSMContext):
    await state.update_data(video_id=message.video.file_id)
    await message.answer("📝 Qism captioni kiriting:")
    await state.set_state(AddPartState.caption)

@dp.message(AddPartState.caption)
async def add_part_caption(message: Message, state: FSMContext):
    data = await state.update_data(caption=message.text)
    success = await db.execute_and_commit(
        "INSERT INTO parts (media_id, part_number, file_id, caption, created_at) VALUES (?, ?, ?, ?, ?)",
        (data['media_id'], data['part_number'], data['video_id'], data['caption'], datetime.now().isoformat())
    )
    if success:
        await db.execute_and_commit("UPDATE media SET total_parts = total_parts + 1 WHERE id = ?", (data['media_id'],))
        media_row = await db.fetch_one("SELECT name FROM media WHERE id = ?", (data['media_id'],))
        media_name = media_row[0] if media_row else "Media"
        await message.answer(f"✅ <b>{media_name}</b> ning <b>{data['part_number']}-qismi</b> qo'shildi!", parse_mode="HTML")
    else:
        await message.answer("❌ Xatolik yuz berdi!")
    await state.clear()

# ================= KO'P QISM QO'SHISH =================
@dp.message(F.text == "➕ Ko'p Qism Qo'shish")
async def add_multiple_parts_start(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("Qaysi animega qism qo'shmoqchisiz?\nAnime nomi yoki kodini kiriting:", parse_mode="HTML")
    await state.set_state(AddMultiplePartsState.select_media)

@dp.message(AddMultiplePartsState.select_media)
async def add_multiple_parts_select_media(message: Message, state: FSMContext):
    query = message.text.strip()
    try:
        code = int(query)
        media_row = await db.fetch_one("SELECT id, name FROM media WHERE code = ?", (code,))
    except ValueError:
        media_row = await db.fetch_one("SELECT id, name FROM media WHERE name LIKE ?", (f"%{query}%",))
    
    if not media_row:
        await message.answer(f"❌ '{query}' bo'yicha media topilmadi! Qayta kiriting:")
        return
    
    media_id = media_row[0] if isinstance(media_row, tuple) else media_row['id']
    media_name = media_row[1] if isinstance(media_row, tuple) else media_row['name']
    await state.update_data(media_id=media_id)
    await message.answer(
        f"📺 <b>{media_name}</b> uchun qismlarni yuboring!\n\n"
        "⚠️ QO'LLANMA:\n"
        "Videolarni tagiga son qo'yib yuboring. Bot tartib bilan qabul qiladi.\n"
        "Masalan: 1-qism videosiga captionga 1 yozing\n\n"
        "Tugatish uchun /done",
        parse_mode="HTML"
    )
    await state.update_data(videos=[])
    await state.set_state(AddMultiplePartsState.videos)

@dp.message(AddMultiplePartsState.videos, F.video)
async def add_multiple_parts_video(message: Message, state: FSMContext):
    data = await state.get_data()
    videos = data.get('videos', [])
    caption = message.caption or ""
    match = re.search(r'^(\d+)', caption)
    part_number = int(match.group(1)) if match else (max([v.get('part_number', 0) for v in videos]) + 1 if videos else 1)
    videos.append({'part_number': part_number, 'file_id': message.video.file_id, 'caption': caption})
    await state.update_data(videos=videos)
    await message.answer(f"✅ {part_number}-qism qabul qilindi! ({len(videos)} ta qism saqlandi)\nTugatish uchun /done", parse_mode="HTML")

@dp.message(AddMultiplePartsState.videos, Command("done"))
async def add_multiple_parts_done(message: Message, state: FSMContext):
    data = await state.get_data()
    media_id = data['media_id']
    videos = data.get('videos', [])
    if not videos:
        await message.answer("❌ Hech qanday video yuborilmagan!")
        return
    videos.sort(key=lambda x: x['part_number'])
    saved = 0
    for video in videos:
        existing = await db.fetch_one("SELECT id FROM parts WHERE media_id = ? AND part_number = ?", (media_id, video['part_number']))
        if not existing:
            success = await db.execute_and_commit(
                "INSERT INTO parts (media_id, part_number, file_id, caption, created_at) VALUES (?, ?, ?, ?, ?)",
                (media_id, video['part_number'], video['file_id'], video['caption'], datetime.now().isoformat())
            )
            if success:
                saved += 1
    if saved > 0:
        await db.execute_and_commit("UPDATE media SET total_parts = total_parts + ? WHERE id = ?", (saved, media_id))
    await message.answer(f"✅ {saved} ta qism qo'shildi!", parse_mode="HTML")
    await state.clear()

# ================= MEDIA TAHRIRLASH =================
@dp.message(F.text == "✏️ Media Tahrirlash")
async def edit_media_start(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("Qaysi animeni tahrirlamoqchisiz?\nAnime nomi yoki kodini kiriting:", parse_mode="HTML")
    await state.set_state(EditMediaState.select)

@dp.message(EditMediaState.select)
async def edit_media_select(message: Message, state: FSMContext):
    query = message.text.strip()
    try:
        code = int(query)
        media_row = await db.fetch_one("SELECT id, name FROM media WHERE code = ?", (code,))
    except ValueError:
        media_row = await db.fetch_one("SELECT id, name FROM media WHERE name LIKE ?", (f"%{query}%",))
    
    if not media_row:
        await message.answer(f"❌ '{query}' bo'yicha media topilmadi! Qayta kiriting:")
        return
    
    media_id = media_row[0] if isinstance(media_row, tuple) else media_row['id']
    media_name = media_row[1] if isinstance(media_row, tuple) else media_row['name']
    await state.update_data(media_id=media_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Nomi", callback_data="edit_field_name")],
        [InlineKeyboardButton(text="🔢 Kod", callback_data="edit_field_code")],
        [InlineKeyboardButton(text="🎭 Janr", callback_data="edit_field_genre")],
        [InlineKeyboardButton(text="📊 Holat", callback_data="edit_field_status")],
        [InlineKeyboardButton(text="🎬 Sezon", callback_data="edit_field_season")],
        [InlineKeyboardButton(text="🎙 Ovoz", callback_data="edit_field_voice")],
        [InlineKeyboardButton(text="🤝 Himoy", callback_data="edit_field_sponsor")],
        [InlineKeyboardButton(text="📀 Sifat", callback_data="edit_field_quality")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_reply")]
    ])
    await message.answer(f"✏️ <b>{media_name}</b> tahrirlash\n\nQaysi maydonni tahrirlamoqchisiz?", reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(EditMediaState.field)

@dp.callback_query(EditMediaState.field, F.data.startswith("edit_field_"))
async def edit_media_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[2]
    await state.update_data(field=field)
    field_names = {
        "name": "yangi nomini",
        "code": "yangi kodni (faqat raqam)",
        "genre": "yangi janrlarini",
        "status": "yangi holatini (ongoing/completed/hiatus)",
        "season": "yangi sezon raqamini",
        "voice": "yangi ovoz(lar)ni",
        "sponsor": "yangi himoy (homiy) ni",
        "quality": "yangi sifatni"
    }
    try:
        await callback.message.edit_text(f"✏️ {field_names.get(field, 'yangi qiymatini')} kiriting:")
    except:
        await safe_send_message(callback.from_user.id, f"✏️ {field_names.get(field, 'yangi qiymatini')} kiriting:")
    await state.set_state(EditMediaState.value)
    await callback.answer()

@dp.message(EditMediaState.value)
async def edit_media_value(message: Message, state: FSMContext):
    data = await state.get_data()
    media_id = data['media_id']
    field = data['field']
    value = message.text.strip()
    
    if field == "code":
        try:
            code = int(value)
            existing = await db.fetch_one("SELECT id FROM media WHERE code = ? AND id != ?", (code, media_id))
            if existing:
                await message.answer("❌ Bunday kod mavjud!")
                return
            await db.execute_and_commit(f"UPDATE media SET code = ? WHERE id = ?", (code, media_id))
            await message.answer(f"✅ Kod '{code}' ga o'zgartirildi!")
        except ValueError:
            await message.answer("❌ Faqat raqam kiriting!")
    elif field == "status":
        if value not in ["ongoing", "completed", "hiatus"]:
            await message.answer("❌ Holat ongoing/completed/hiatus bo'lishi kerak!")
            return
        await db.execute_and_commit(f"UPDATE media SET status = ? WHERE id = ?", (value, media_id))
        await message.answer(f"✅ Holat '{value}' ga o'zgartirildi!")
    elif field == "season":
        try:
            season = int(value)
            await db.execute_and_commit(f"UPDATE media SET season = ? WHERE id = ?", (season, media_id))
            await message.answer(f"✅ Sezon {season} ga o'zgartirildi!")
        except ValueError:
            await message.answer("❌ Faqat raqam kiriting!")
    else:
        await db.execute_and_commit(f"UPDATE media SET {field} = ? WHERE id = ?", (value, media_id))
        await message.answer(f"✅ {field} o'zgartirildi!")
    
    await state.clear()

# ================= QISMNI TAHRIRLASH =================
@dp.message(F.text == "✏️ Qismni Tahrirlash")
async def edit_part_start(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("Qaysi animega tegishli qismni tahrirlamoqchisiz?\nAnime nomi yoki kodini kiriting:", parse_mode="HTML")
    await state.set_state(EditPartState.select_media)

@dp.message(EditPartState.select_media)
async def edit_part_select_media(message: Message, state: FSMContext):
    query = message.text.strip()
    try:
        code = int(query)
        media_row = await db.fetch_one("SELECT id, name FROM media WHERE code = ?", (code,))
    except ValueError:
        media_row = await db.fetch_one("SELECT id, name FROM media WHERE name LIKE ?", (f"%{query}%",))
    
    if not media_row:
        await message.answer(f"❌ '{query}' bo'yicha media topilmadi! Qayta kiriting:")
        return
    
    media_id = media_row[0] if isinstance(media_row, tuple) else media_row['id']
    media_name = media_row[1] if isinstance(media_row, tuple) else media_row['name']
    await state.update_data(media_id=media_id)
    
    # Qismlar ro'yxatini ko'rsatish
    parts_rows = await db.fetch_all("SELECT id, part_number FROM parts WHERE media_id = ? ORDER BY part_number", (media_id,))
    parts_list = list(parts_rows) if parts_rows else []
    
    if not parts_list:
        await message.answer("❌ Bu animeda hech qanday qism mavjud emas!")
        await state.clear()
        return
    
    builder = InlineKeyboardBuilder()
    for part in parts_list:
        part_id = part[0] if isinstance(part, tuple) else part['id']
        part_num = part[1] if isinstance(part, tuple) else part['part_number']
        builder.button(text=f"📹 {part_num}-qism", callback_data=f"edit_part_select_{part_id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_reply"))
    
    await message.answer(f"📺 <b>{media_name}</b>\n\nQism tanlang:", reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(EditPartState.select_part)

@dp.callback_query(EditPartState.select_part, F.data.startswith("edit_part_select_"))
async def edit_part_select_part(callback: CallbackQuery, state: FSMContext):
    part_id = int(callback.data.split("_")[3])
    await state.update_data(part_id=part_id)
    
    part_row = await db.fetch_one("SELECT part_number, media_id FROM parts WHERE id = ?", (part_id,))
    if not part_row:
        await callback.answer("Qism topilmadi!")
        return
    
    part_num = part_row[0] if isinstance(part_row, tuple) else part_row['part_number']
    media_id = part_row[1] if isinstance(part_row, tuple) else part_row['media_id']
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📹 Video", callback_data="edit_part_video")],
        [InlineKeyboardButton(text="📝 Caption", callback_data="edit_part_caption")],
        [InlineKeyboardButton(text="🔢 Qism raqami", callback_data="edit_part_number")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data="edit_part_delete")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"back_to_parts_{media_id}")]
    ])
    
    try:
        await callback.message.edit_text(f"✏️ {part_num}-qismni tahrirlash\n\nQaysi maydonni tahrirlamoqchisiz?", reply_markup=keyboard, parse_mode="HTML")
    except:
        await safe_send_message(callback.from_user.id, f"✏️ {part_num}-qismni tahrirlash\n\nQaysi maydonni tahrirlamoqchisiz?", reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(EditPartState.field)
    await callback.answer()

@dp.callback_query(EditPartState.field, F.data == "edit_part_video")
async def edit_part_video_request(callback: CallbackQuery, state: FSMContext):
    await state.update_data(field="video")
    try:
        await callback.message.edit_text("✏️ Yangi videoni yuboring:")
    except:
        await safe_send_message(callback.from_user.id, "✏️ Yangi videoni yuboring:")
    await state.set_state(EditPartState.value)
    await callback.answer()

@dp.callback_query(EditPartState.field, F.data == "edit_part_caption")
async def edit_part_caption_request(callback: CallbackQuery, state: FSMContext):
    await state.update_data(field="caption")
    try:
        await callback.message.edit_text("✏️ Yangi captionni kiriting:")
    except:
        await safe_send_message(callback.from_user.id, "✏️ Yangi captionni kiriting:")
    await state.set_state(EditPartState.value)
    await callback.answer()

@dp.callback_query(EditPartState.field, F.data == "edit_part_number")
async def edit_part_number_request(callback: CallbackQuery, state: FSMContext):
    await state.update_data(field="number")
    try:
        await callback.message.edit_text("✏️ Yangi qism raqamini kiriting:")
    except:
        await safe_send_message(callback.from_user.id, "✏️ Yangi qism raqamini kiriting:")
    await state.set_state(EditPartState.value)
    await callback.answer()

@dp.callback_query(EditPartState.field, F.data == "edit_part_delete")
async def edit_part_delete(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    part_id = data['part_id']
    
    part_row = await db.fetch_one("SELECT media_id, part_number FROM parts WHERE id = ?", (part_id,))
    if part_row:
        media_id = part_row[0] if isinstance(part_row, tuple) else part_row['media_id']
        part_num = part_row[1] if isinstance(part_row, tuple) else part_row['part_number']
        
        await db.execute_and_commit("DELETE FROM parts WHERE id = ?", (part_id,))
        await db.execute_and_commit("UPDATE media SET total_parts = total_parts - 1 WHERE id = ?", (media_id,))
        
        await callback.message.edit_text(f"✅ {part_num}-qism o'chirildi!")
        await state.clear()
    else:
        await callback.message.edit_text("❌ Qism topilmadi!")
    await callback.answer()

@dp.message(EditPartState.value, F.video)
async def edit_part_video_value(message: Message, state: FSMContext):
    data = await state.get_data()
    part_id = data['part_id']
    await db.execute_and_commit("UPDATE parts SET file_id = ? WHERE id = ?", (message.video.file_id, part_id))
    await message.answer("✅ Video o'zgartirildi!")
    await state.clear()

@dp.message(EditPartState.value, F.text)
async def edit_part_text_value(message: Message, state: FSMContext):
    data = await state.get_data()
    part_id = data['part_id']
    field = data['field']
    value = message.text.strip()
    
    if field == "number":
        try:
            new_num = int(value)
            part_row = await db.fetch_one("SELECT media_id FROM parts WHERE id = ?", (part_id,))
            if part_row:
                media_id = part_row[0] if isinstance(part_row, tuple) else part_row['media_id']
                existing = await db.fetch_one("SELECT id FROM parts WHERE media_id = ? AND part_number = ? AND id != ?", (media_id, new_num, part_id))
                if existing:
                    await message.answer(f"⚠️ {new_num}-qism mavjud!")
                    return
            await db.execute_and_commit("UPDATE parts SET part_number = ? WHERE id = ?", (new_num, part_id))
            await message.answer(f"✅ Qism raqami {new_num} ga o'zgartirildi!")
        except ValueError:
            await message.answer("❌ Faqat raqam kiriting!")
    elif field == "caption":
        await db.execute_and_commit("UPDATE parts SET caption = ? WHERE id = ?", (value, part_id))
        await message.answer("✅ Caption o'zgartirildi!")
    
    await state.clear()

# ================= STATISTIKA =================
@dp.message(F.text == "📊 Statistika")
async def show_stats(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Siz admin emassiz!")
        return
    
    users_row = await db.fetch_one("SELECT COUNT(*) FROM users WHERE is_blocked = 0")
    media_row = await db.fetch_one("SELECT COUNT(*) FROM media")
    parts_row = await db.fetch_one("SELECT COUNT(*) FROM parts")
    views_row = await db.fetch_one("SELECT SUM(views) FROM media")
    admins_row = await db.fetch_one("SELECT COUNT(*) FROM admins")
    
    users = users_row[0] if users_row else 0
    media = media_row[0] if media_row else 0
    parts = parts_row[0] if parts_row else 0
    views = views_row[0] if views_row and views_row[0] else 0
    admins = admins_row[0] if admins_row else 0
    
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: {users}\n"
        f"🎬 Media: {media}\n"
        f"📹 Qismlar: {parts}\n"
        f"👁️ Ko'rishlar: {views}\n"
        f"👑 Adminlar: {admins}",
        parse_mode="HTML"
    )

# ================= XABAR YUBORISH =================
@dp.message(F.text == "📢 Xabar Yuborish")
async def broadcast_start(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("📢 Xabar yuborish\n\nXabaringizni kiriting:", parse_mode="HTML")
    await state.set_state(BroadcastState.message)

@dp.message(BroadcastState.message)
async def broadcast_send(message: Message, state: FSMContext):
    users_rows = await db.fetch_all("SELECT id FROM users WHERE is_blocked = 0")
    users = list(users_rows) if users_rows else []
    sent = 0
    
    for user in users:
        user_id = user[0] if isinstance(user, tuple) else user['id']
        try:
            if message.photo:
                await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption, parse_mode="HTML")
            elif message.video:
                await bot.send_video(user_id, message.video.file_id, caption=message.caption, parse_mode="HTML")
            else:
                await bot.send_message(user_id, message.text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            logger.error(f"Xabar yuborilmadi {user_id}: {e}")
    
    await message.answer(f"✅ {sent}/{len(users)} ta foydalanuvchiga yuborildi!")
    await state.clear()

# ================= MAJBURIY KANAL BOSHQARUVI =================
@dp.message(F.text == "🔗 Majburiy A'zo")
async def forced_subscribe_menu(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Siz admin emassiz!")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="forced_add")],
        [InlineKeyboardButton(text="❌ Kanal o'chirish", callback_data="forced_remove")],
        [InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="forced_list")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_reply")]
    ])
    
    await message.answer(
        "🔗 <b>Majburiy a'zolik boshqaruvi</b>\n\n"
        "Bu yerdan botdan foydalanish uchun majburiy a'zo bo'linadigan kanallarni boshqarishingiz mumkin.\n\n"
        "⚠️ <b>Eslatma:</b> Bot kanalda admin bo'lishi shart EMAS!", 
        reply_markup=keyboard, 
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "forced_add")
async def forced_add_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q!", show_alert=True)
        return
    await state.set_state(ForcedChannelState.waiting_for_channel)
    await callback.message.edit_text(
        "➕ <b>Kanal qo'shish</b>\n\n"
        "Kanal username yoki linkini yuboring:\n"
        "Masalan: @kanal yoki https://t.me/kanal\n\n"
        "⚠️ Bot kanalda admin bo'lishi shart EMAS!",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(ForcedChannelState.waiting_for_channel)
async def forced_add_channel(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Siz admin emassiz!")
        await state.clear()
        return
    
    channel_input = message.text.strip()
    
    if channel_input.startswith("https://t.me/"):
        parts = channel_input.split("/")
        username = parts[-1].split("?")[0]
        channel_username = f"@{username}"
    elif channel_input.startswith("@"):
        channel_username = channel_input
    else:
        channel_username = f"@{channel_input}"
    
    clean_username = channel_username.replace('@', '').strip()
    
    try:
        chat = await bot.get_chat(f"@{clean_username}")
        channel_id = chat.id
        
        success = await db.execute_and_commit('''
        INSERT OR IGNORE INTO forced_channels (channel_username, channel_id, is_active, added_at)
        VALUES (?, ?, ?, ?)
        ''', (channel_username, channel_id, 1, datetime.now().isoformat()))
        
        if success:
            await message.answer(f"✅ <b>{channel_username}</b> majburiy a'zolik ro'yxatiga qo'shildi!", parse_mode="HTML")
        else:
            await message.answer(f"⚠️ {channel_username} allaqachon ro'yxatda mavjud!")
    except Exception as e:
        logger.error(f"Kanal qo'shish xatosi: {e}")
        await message.answer(f"❌ <b>{channel_username}</b> kanali topilmadi!", parse_mode="HTML")
    
    await state.clear()

@dp.callback_query(F.data == "forced_remove")
async def forced_remove_list(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q!", show_alert=True)
        return
    
    rows = await db.fetch_all("SELECT id, channel_username FROM forced_channels WHERE is_active = 1 ORDER BY channel_username")
    channels = list(rows) if rows else []
    
    if not channels:
        await callback.message.edit_text("📭 <b>Majburiy kanallar ro'yxati bo'sh.</b>", parse_mode="HTML")
        await callback.answer()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for ch in channels:
        ch_id = ch[0] if isinstance(ch, tuple) else ch['id']
        channel_username = ch[1] if isinstance(ch, tuple) else ch['channel_username']
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"❌ {channel_username}", callback_data=f"forced_del_{ch_id}")
        ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_forced_menu")
    ])
    
    await callback.message.edit_text("❌ <b>O'chirmoqchi bo'lgan kanalni tanlang:</b>", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("forced_del_"))
async def forced_remove_channel(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q!", show_alert=True)
        return
    
    ch_id = int(callback.data.split("_")[2])
    channel_row = await db.fetch_one("SELECT channel_username FROM forced_channels WHERE id = ?", (ch_id,))
    
    if channel_row:
        channel_username = channel_row[0] if isinstance(channel_row, tuple) else channel_row['channel_username']
        await db.execute_and_commit("DELETE FROM forced_channels WHERE id = ?", (ch_id,))
        await callback.message.edit_text(f"✅ <b>{channel_username}</b> o'chirildi!", parse_mode="HTML")
    else:
        await callback.message.edit_text("❌ Kanal topilmadi!", parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "forced_list")
async def forced_list(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q!", show_alert=True)
        return
    
    rows = await db.fetch_all("SELECT channel_username, is_active, added_at FROM forced_channels ORDER BY channel_username")
    channels = list(rows) if rows else []
    
    if not channels:
        text = "📭 <b>Majburiy kanallar ro'yxati bo'sh.</b>"
    else:
        text = "📋 <b>Majburiy kanallar ro'yxati:</b>\n\n"
        for ch in channels:
            ch_username = ch[0] if isinstance(ch, tuple) else ch['channel_username']
            is_active = ch[1] if isinstance(ch, tuple) else ch['is_active']
            added_at = ch[2] if isinstance(ch, tuple) else ch['added_at']
            status = "✅ Aktiv" if is_active else "❌ Noaktiv"
            date = added_at[:10] if added_at else "Noma'lum"
            text += f"• {ch_username}\n  {status} | Qo'shilgan: {date}\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_forced_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "back_to_forced_menu")
async def back_to_forced_menu(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="forced_add")],
        [InlineKeyboardButton(text="❌ Kanal o'chirish", callback_data="forced_remove")],
        [InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="forced_list")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_reply")]
    ])
    
    await callback.message.edit_text(
        "🔗 <b>Majburiy a'zolik boshqaruvi</b>\n\n"
        "Bu yerdan botdan foydalanish uchun majburiy a'zo bo'linadigan kanallarni boshqarishingiz mumkin.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

# ================= ADMIN QO'SHISH =================
@dp.message(F.text == "👑 Admin Qo'shish")
async def admin_manage(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        await message.answer("❌ Faqat ownerlar admin qo'shishi mumkin!")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Admin Qo'shish", callback_data="admin_add")],
        [InlineKeyboardButton(text="❌ Admin Chiqarish", callback_data="admin_remove")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_reply")]
    ])
    await message.answer("Admin boshqaruvi:", reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(AdminManageState.action)

@dp.callback_query(AdminManageState.action, F.data == "admin_add")
async def admin_add_request(callback: CallbackQuery, state: FSMContext):
    if not await is_owner(callback.from_user.id):
        await callback.answer("❌ Faqat ownerlar admin qo'shishi mumkin!", show_alert=True)
        return
    await state.update_data(action="add")
    await callback.message.edit_text("➕ Yangi admin ID sini kiriting:", parse_mode="HTML")
    await state.set_state(AdminManageState.user_id)
    await callback.answer()

@dp.callback_query(AdminManageState.action, F.data == "admin_remove")
async def admin_remove_request(callback: CallbackQuery, state: FSMContext):
    if not await is_owner(callback.from_user.id):
        await callback.answer("❌ Faqat ownerlar admin chiqarishi mumkin!", show_alert=True)
        return
    await state.update_data(action="remove")
    
    rows = await db.fetch_all("SELECT user_id FROM admins WHERE user_id NOT IN (?, ?)", (ADMINS[0], ADMINS[1] if len(ADMINS) > 1 else 0))
    admins = list(rows) if rows else []
    
    if admins:
        text = "❌ Admin chiqarish:\n\nMavjud adminlar:\n" + "\n".join([f"• {a[0]}" for a in admins]) + "\n\nO'chirmoqchi bo'lgan ID ni kiriting:"
        await callback.message.edit_text(text, parse_mode="HTML")
    else:
        await callback.message.edit_text("❌ O'chirish mumkin bo'lgan admin yo'q!", parse_mode="HTML")
        await state.clear()
    await state.set_state(AdminManageState.user_id)
    await callback.answer()

@dp.message(AdminManageState.user_id)
async def admin_manage_user_id(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        data = await state.get_data()
        if data['action'] == "add":
            success = await db.execute_and_commit(
                "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
                (user_id, message.from_user.id, datetime.now().isoformat())
            )
            await message.answer(f"✅ {user_id} admin qo'shildi!" if success else f"⚠️ {user_id} allaqachon admin!")
            try:
                await bot.send_message(user_id, "🎉 Siz admin etib tayinlandingiz!")
            except:
                pass
        else:
            if user_id in ADMINS:
                await message.answer("❌ Ownerlarni o'chirib bo'lmaydi!")
            else:
                success = await db.execute_and_commit("DELETE FROM admins WHERE user_id = ?", (user_id,))
                await message.answer(f"✅ {user_id} adminlikdan chiqarildi!" if success else f"⚠️ {user_id} admin emas!")
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting!")
    await state.clear()

# ================= POST QILISH =================
@dp.message(F.text == "📨 Post Qilish")
async def post_start(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("📨 Post qilish\n\nPost qilmoqchi bo'lgan media nomi yoki kodini kiriting:", parse_mode="HTML")
    await state.set_state(PostState.media_id)

@dp.message(PostState.media_id)
async def post_media_id(message: Message, state: FSMContext):
    query = message.text.strip()
    try:
        code = int(query)
        media_row = await db.fetch_one("SELECT id, name, code, description, total_parts, status, season, genre, voice, sponsor, quality, image_url FROM media WHERE code = ?", (code,))
    except ValueError:
        media_row = await db.fetch_one("SELECT id, name, code, description, total_parts, status, season, genre, voice, sponsor, quality, image_url FROM media WHERE name LIKE ?", (f"%{query}%",))
    
    if not media_row:
        await message.answer(f"❌ '{query}' bo'yicha media topilmadi!")
        return
    
    media_id = media_row[0] if isinstance(media_row, tuple) else media_row['id']
    name = media_row[1] if isinstance(media_row, tuple) else media_row['name']
    code = media_row[2] if isinstance(media_row, tuple) else media_row['code']
    total_parts = media_row[4] if isinstance(media_row, tuple) else media_row['total_parts']
    status = media_row[5] if isinstance(media_row, tuple) else media_row['status']
    season = media_row[6] if isinstance(media_row, tuple) else media_row['season']
    genre = media_row[7] if isinstance(media_row, tuple) else media_row['genre']
    voice = media_row[8] if isinstance(media_row, tuple) else media_row['voice']
    sponsor = media_row[9] if isinstance(media_row, tuple) else media_row['sponsor']
    quality = media_row[10] if isinstance(media_row, tuple) else media_row['quality']
    image = media_row[11] if isinstance(media_row, tuple) else media_row['image_url']
    
    await state.update_data(media_id=media_id, media_image=image)
    
    status_text = {"ongoing": "🟢 Davom etmoqda", "completed": "✅ Tugallangan", "hiatus": "⏸ To'xtatilgan"}.get(status, "Noma'lum")
    voice_text = voice if voice else f"{AUTHOR_USERNAME}"
    sponsor_text = sponsor if sponsor else "AniCity Rasmiy"
    
    info_text = (
        f"📨 <b>Post ma'lumotlari</b>\n\n"
        f"🎬 Nomi: {name}\n"
        f"🔢 Kod: {code}\n"
        f"🎭 Janr: {genre}\n"
        f"🎬 Sezon: {season}\n"
        f"📹 Qismlar: {total_parts} ta\n"
        f"📊 Holat: {status_text}\n"
        f"🎙 Ovoz: {voice_text}\n"
        f"🤝 Himoy: {sponsor_text}\n"
        f"📀 Sifat: {quality}\n\n"
        "Endi post qilmoqchi bo'lgan kanal linkini yuboring:\n"
        "Masalan: @kanal yoki https://t.me/kanal"
    )
    await message.answer(info_text, parse_mode="HTML")
    await state.set_state(PostState.channel)

@dp.message(PostState.channel)
async def post_channel(message: Message, state: FSMContext):
    channel_input = message.text.strip()
    if channel_input.startswith("https://t.me/"):
        parts = channel_input.split("/")
        username = parts[-1].split("?")[0]
        channel = f"@{username}"
    elif channel_input.startswith("@"):
        channel = channel_input
    else:
        channel = f"@{channel_input}"
    
    await state.update_data(channel=channel)
    
    data = await state.get_data()
    media_id = data['media_id']
    
    media_row = await db.fetch_one("SELECT name, code, total_parts, status, season, genre, voice, sponsor, quality, image_url FROM media WHERE id = ?", (media_id,))
    if not media_row:
        await message.answer("❌ Media topilmadi!")
        return
    
    name = media_row[0] if isinstance(media_row, tuple) else media_row['name']
    code = media_row[1] if isinstance(media_row, tuple) else media_row['code']
    total_parts = media_row[2] if isinstance(media_row, tuple) else media_row['total_parts']
    status = media_row[3] if isinstance(media_row, tuple) else media_row['status']
    season = media_row[4] if isinstance(media_row, tuple) else media_row['season']
    genre = media_row[5] if isinstance(media_row, tuple) else media_row['genre']
    voice = media_row[6] if isinstance(media_row, tuple) else media_row['voice']
    sponsor = media_row[7] if isinstance(media_row, tuple) else media_row['sponsor']
    quality = media_row[8] if isinstance(media_row, tuple) else media_row['quality']
    image = media_row[9] if isinstance(media_row, tuple) else media_row['image_url']
    
    status_text = {"ongoing": "🟢 Davom etmoqda", "completed": "✅ Tugallangan", "hiatus": "⏸ To'xtatilgan"}.get(status, "Noma'lum")
    voice_text = voice if voice else f"{AUTHOR_USERNAME}"
    sponsor_text = sponsor if sponsor else "AniCity Rasmiy"
    
    post_text = f"""
┌─────────────────────────────────
🎬 <b>{name}</b>
└─────────────────────────────────

┌─────────────────────────────────
• Janr: {genre}
• Sezon: {season}
• Qism: {total_parts}
• Holati: {status_text}
• Ovoz: {voice_text}
• Himoy: {sponsor_text}
• Sifat: {quality}
└─────────────────────────────────

🔢 Kod: <code>{code}</code>
📢 Kanal: @AniCity_Rasmiy
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_post")],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data="cancel_post")]
    ])
    
    await message.answer(post_text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(PostState.confirm)

@dp.callback_query(PostState.confirm, F.data == "confirm_post")
async def post_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    media_id = data['media_id']
    channel = data['channel']
    image = data.get('media_image')
    
    media_row = await db.fetch_one("SELECT name, code, total_parts, status, season, genre, voice, sponsor, quality FROM media WHERE id = ?", (media_id,))
    if not media_row:
        await callback.message.edit_text("❌ Media topilmadi!")
        return
    
    name = media_row[0] if isinstance(media_row, tuple) else media_row['name']
    code = media_row[1] if isinstance(media_row, tuple) else media_row['code']
    total_parts = media_row[2] if isinstance(media_row, tuple) else media_row['total_parts']
    status = media_row[3] if isinstance(media_row, tuple) else media_row['status']
    season = media_row[4] if isinstance(media_row, tuple) else media_row['season']
    genre = media_row[5] if isinstance(media_row, tuple) else media_row['genre']
    voice = media_row[6] if isinstance(media_row, tuple) else media_row['voice']
    sponsor = media_row[7] if isinstance(media_row, tuple) else media_row['sponsor']
    quality = media_row[8] if isinstance(media_row, tuple) else media_row['quality']
    
    status_text = {"ongoing": "🟢 Davom etmoqda", "completed": "✅ Tugallangan", "hiatus": "⏸ To'xtatilgan"}.get(status, "Noma'lum")
    voice_text = voice if voice else f"{AUTHOR_USERNAME}"
    sponsor_text = sponsor if sponsor else "AniCity Rasmiy"
    
    post_text = f"""
┌─────────────────────────────────
🎬 <b>{name}</b>
└─────────────────────────────────

┌─────────────────────────────────
• Janr: {genre}
• Sezon: {season}
• Qism: {total_parts}
• Holati: {status_text}
• Ovoz: {voice_text}
• Himoy: {sponsor_text}
• Sifat: {quality}
└─────────────────────────────────

🔢 Kod: <code>{code}</code>
📢 Kanal: @AniCity_Rasmiy
"""
    
    bot_info = await bot.get_me()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Tomosha qilish", url=f"https://t.me/{bot_info.username}?start=code_{code}")]
    ])
    
    try:
        if image:
            await bot.send_photo(chat_id=channel, photo=image, caption=post_text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=channel, text=post_text, reply_markup=keyboard, parse_mode="HTML")
        await callback.message.edit_text(f"✅ Post muvaffaqiyatli yuborildi!\n\nKanal: {channel}")
    except Exception as e:
        await callback.message.edit_text(f"❌ Xatolik: {e}")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "cancel_post")
async def post_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer("❌ Post bekor qilindi.")
    await callback.answer()

# ================= QISMNI POST QILISH =================
@dp.message(F.text == "🎬 Qismni Post Qilish")
async def part_post_start(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("🎬 Qismni post qilish\n\nPost qilmoqchi bo'lgan media nomi yoki kodini kiriting:", parse_mode="HTML")
    await state.set_state(PartPostState.media_id)

@dp.message(PartPostState.media_id)
async def part_post_media_id(message: Message, state: FSMContext):
    query = message.text.strip()
    try:
        code = int(query)
        media_row = await db.fetch_one("SELECT id, name, code, image_url FROM media WHERE code = ?", (code,))
    except ValueError:
        media_row = await db.fetch_one("SELECT id, name, code, image_url FROM media WHERE name LIKE ?", (f"%{query}%",))
    
    if not media_row:
        await message.answer(f"❌ '{query}' bo'yicha media topilmadi!")
        return
    
    media_id = media_row[0] if isinstance(media_row, tuple) else media_row['id']
    name = media_row[1] if isinstance(media_row, tuple) else media_row['name']
    code = media_row[2] if isinstance(media_row, tuple) else media_row['code']
    image = media_row[3] if isinstance(media_row, tuple) else media_row['image_url']
    
    await state.update_data(media_id=media_id, media_name=name, media_code=code, media_image=image)
    
    # Qismlar ro'yxatini ko'rsatish
    parts_rows = await db.fetch_all("SELECT id, part_number FROM parts WHERE media_id = ? ORDER BY part_number", (media_id,))
    parts_list = list(parts_rows) if parts_rows else []
    
    if not parts_list:
        await message.answer("❌ Bu animeda hech qanday qism mavjud emas!")
        await state.clear()
        return
    
    builder = InlineKeyboardBuilder()
    for part in parts_list:
        part_id = part[0] if isinstance(part, tuple) else part['id']
        part_num = part[1] if isinstance(part, tuple) else part['part_number']
        builder.button(text=f"📹 {part_num}-qism", callback_data=f"part_post_select_{part_id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin_reply"))
    
    await message.answer(f"📺 <b>{name}</b> (Kod: {code})\n\nQaysi qismni post qilmoqchisiz?", reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(PartPostState.part_id)

@dp.callback_query(PartPostState.part_id, F.data.startswith("part_post_select_"))
async def part_post_select_part(callback: CallbackQuery, state: FSMContext):
    part_id = int(callback.data.split("_")[3])
    await state.update_data(part_id=part_id)
    
    part_row = await db.fetch_one("SELECT part_number FROM parts WHERE id = ?", (part_id,))
    if not part_row:
        await callback.answer("Qism topilmadi!")
        return
    
    part_num = part_row[0] if isinstance(part_row, tuple) else part_row['part_number']
    data = await state.get_data()
    media_name = data.get('media_name')
    media_code = data.get('media_code')
    
    await callback.message.edit_text(
        f"✅ <b>{media_name}</b> - {part_num}-qism topildi!\n\n"
        f"🎭 Kod: {media_code}\n\n"
        "Endi post qilmoqchi bo'lgan kanal linkini yuboring:\n"
        "Masalan: @kanal yoki https://t.me/kanal",
        parse_mode="HTML"
    )
    await state.update_data(part_number=part_num)
    await state.set_state(PartPostState.channel)
    await callback.answer()

@dp.message(PartPostState.channel)
async def part_post_channel(message: Message, state: FSMContext):
    channel_input = message.text.strip()
    if channel_input.startswith("https://t.me/"):
        parts = channel_input.split("/")
        username = parts[-1].split("?")[0]
        channel = f"@{username}"
    elif channel_input.startswith("@"):
        channel = channel_input
    else:
        channel = f"@{channel_input}"
    
    await state.update_data(channel=channel)
    
    data = await state.get_data()
    media_name = data.get('media_name')
    media_code = data.get('media_code')
    part_num = data.get('part_number')
    media_image = data.get('media_image')
    
    post_text = f"""
┌─────────────────────────────────
🎬 <b>{media_name}</b>
└─────────────────────────────────

┌─────────────────────────────────
• {part_num}-qism
• Anime KODI: {media_code}
└─────────────────────────────────

📢 Kanal: @AniCity_Rasmiy
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_part_post")],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data="cancel_post")]
    ])
    
    await message.answer(post_text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(PartPostState.confirm)

@dp.callback_query(PartPostState.confirm, F.data == "confirm_part_post")
async def part_post_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    media_name = data.get('media_name')
    media_code = data.get('media_code')
    part_num = data.get('part_number')
    media_image = data.get('media_image')
    channel = data.get('channel')
    
    bot_info = await bot.get_me()
    
    post_text = f"""
┌─────────────────────────────────
🎬 <b>{media_name}</b>
└─────────────────────────────────

┌─────────────────────────────────
• {part_num}-qism
• Anime KODI: {media_code}
└─────────────────────────────────

📢 Kanal: @AniCity_Rasmiy
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎬 {part_num}-qismni tomosha qilish", url=f"https://t.me/{bot_info.username}?start=code_{media_code}&part={part_num}")]
    ])
    
    try:
        if media_image:
            await bot.send_photo(chat_id=channel, photo=media_image, caption=post_text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=channel, text=post_text, reply_markup=keyboard, parse_mode="HTML")
        await callback.message.edit_text(f"✅ Qism post qilindi!\n\nKanal: {channel}")
    except Exception as e:
        await callback.message.edit_text(f"❌ Xatolik: {e}")
    await state.clear()
    await callback.answer()

# ================= QOLGAN CALLBACKLAR =================
@dp.callback_query(F.data == "search_by_code")
async def search_by_code_start(callback: CallbackQuery, state: FSMContext):
    await update_user_activity(callback.from_user.id)
    await state.set_state(CodeSearchState.waiting_for_code)
    text = "🔍 Qidirilishi kerak bo'lgan anime yoki drama kodini yuboring"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_start")]])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except:
        await safe_send_message(callback.from_user.id, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.message(CodeSearchState.waiting_for_code)
async def search_by_code(message: Message, state: FSMContext):
    await update_user_activity(message.from_user.id)
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Iltimos, faqat raqam (kod) yuboring!")
        return
    code = int(text)
    media_row = await db.fetch_one("SELECT id, name FROM media WHERE code = ?", (code,))
    if media_row:
        media_id = media_row[0] if isinstance(media_row, tuple) else media_row['id']
        media_name = media_row[1] if isinstance(media_row, tuple) else media_row['name']
        await message.answer(f"✅ <b>{media_name}</b> topildi!\n🔢 Kod: {code}", parse_mode="HTML")
    else:
        await message.answer(f"❌ '{code}' kodli media topilmadi!")
    await state.clear()

@dp.callback_query(F.data == "search_anime")
async def search_anime_start(callback: CallbackQuery, state: FSMContext):
    await update_user_activity(callback.from_user.id)
    await state.update_data(search_type="anime")
    await state.set_state(SearchState.query)
    text = "🔍 Qidirilishi kerak bo'lgan anime nomini yuboring"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_start")]])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except:
        await safe_send_message(callback.from_user.id, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "search_drama")
async def search_drama_start(callback: CallbackQuery, state: FSMContext):
    await update_user_activity(callback.from_user.id)
    await state.update_data(search_type="drama")
    await state.set_state(SearchState.query)
    text = "🔍 Qidirilishi kerak bo'lgan drama nomini yuboring"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_start")]])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except:
        await safe_send_message(callback.from_user.id, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.message(SearchState.query)
async def search_media_query(message: Message, state: FSMContext):
    query = message.text.strip()
    data = await state.get_data()
    search_type = data.get('search_type', 'anime')
    media_type = "anime" if search_type == "anime" else "drama"
    
    rows = await db.fetch_all(
        "SELECT id, name, code FROM media WHERE type = ? AND name LIKE ? ORDER BY name",
        (media_type, f"%{query}%")
    )
    results = list(rows) if rows else []
    
    if not results:
        await safe_send_message(message.chat.id, f"❌ '{query}' bo'yicha hech narsa topilmadi!")
        await state.clear()
        return
    
    builder = InlineKeyboardBuilder()
    for res in results:
        media_id = res[0] if isinstance(res, tuple) else res['id']
        name = res[1] if isinstance(res, tuple) else res['name']
        code = res[2] if isinstance(res, tuple) else res['code']
        builder.button(text=f"🎬 {name} [{code}]", callback_data=f"view_media_{media_id}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_start"))
    
    await safe_send_message(message.chat.id, f"🔍 '{query}' bo'yicha topilganlar ({len(results)}):", reply_markup=builder.as_markup())
    await state.clear()

@dp.callback_query(F.data == "search_image")
async def search_image_start(callback: CallbackQuery, state: FSMContext):
    await update_user_activity(callback.from_user.id)
    await state.set_state(ImageSearchState.waiting_for_image)
    text = (
        "🖼 <b>RASM ORQALI ANIME QIDIRUV</b>\n\n"
        "Qidirmoqchi bo'lgan animening rasmni yuboring.\n\n"
        "📌 <b>QO'LLANMA:</b>\n"
        "• Animening skrinshotini yuboring\n"
        "• Anime posteri yoki banneri EMAS\n\n"
        "Bot rasmni tahlil qilib, eng mos animeni topadi."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_start")]])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except:
        await safe_send_message(callback.from_user.id, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.message(ImageSearchState.waiting_for_image, F.photo)
async def search_by_image(message: Message, state: FSMContext):
    await update_user_activity(message.from_user.id)
    await message.answer("🖼 Rasm qabul qilindi! 🔍 Qidiruv boshlanmoqda...")
    
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    image_data = file_bytes.read()
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post('https://api.trace.moe/search', data={'image': image_base64}) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if result.get('result') and len(result['result']) > 0:
                        top_result = result['result'][0]
                        anime_name = top_result.get('filename', 'Noma\'lum')
                        similarity = top_result.get('similarity', 0) * 100
                        episode = top_result.get('episode', '?')
                        await message.answer(f"🔍 Topilgan anime: <b>{anime_name}</b>\n📊 Aniqlik: {similarity:.1f}%\n📺 Epizod: {episode}", parse_mode="HTML")
                    else:
                        await message.answer("❌ Hech qanday anime topilmadi!")
                else:
                    await message.answer("❌ API xatolik! Keyinroq urinib ko'ring.")
        except Exception as e:
            logger.error(f"Rasm qidiruv xatosi: {e}")
            await message.answer("❌ Xatolik yuz berdi! Keyinroq urinib ko'ring.")
    
    await state.clear()

@dp.message(ImageSearchState.waiting_for_image)
async def search_by_image_invalid(message: Message, state: FSMContext):
    await message.answer("❌ Iltimos, rasm yuboring!")
    await state.clear()

@dp.callback_query(F.data == "guide")
async def guide_start(callback: CallbackQuery):
    await update_user_activity(callback.from_user.id)
    text = (
        "📚 <b>Botni ishlatish bo'yicha qo'llanma:</b>\n\n"
        "🔍 <b>Kod orqali qidiruv</b> - Anime kodini yuborib topish\n"
        "🎬 <b>Anime Qidirish</b> - Botda mavjud bo'lgan animelarni qidirish\n"
        "🎭 <b>Drama Qidirish</b> - Botda mavjud bo'lgan dramalarni qidirish\n"
        "🖼 <b>Rasm Orqali Anime Qidiruv</b> - Nomini topa olmayotgan animeingizni rasm orqali topish\n"
        "💸 <b>Reklama</b> - bot adminlari bilan reklama yoki homiylik yuzasidan aloqaga chiqish\n"
        "📓 <b>Ro'yxat</b> - Botga joylangan Anime va Dramalar ro'yxati\n\n"
        f"👨‍💻 <b>Muallif:</b> <a href='{AUTHOR_LINK}'>{AUTHOR_USERNAME}</a>\n"
        f"🆘 <b>Yordam:</b> <a href='{AUTHOR_LINK}'>{AUTHOR_USERNAME}</a>\n\n"
        f"🆔 <b>Botdagi ID ingiz:</b> <code>{callback.from_user.id}</code>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_start")]])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except:
        await safe_send_message(callback.from_user.id, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "advertisement")
async def advertisement_start(callback: CallbackQuery):
    await update_user_activity(callback.from_user.id)
    text = (
        "📌 <b>Reklama va homiylik masalasida admin bilan bog'laning</b>\n\n"
        f"👨‍💻 <b>Muallif:</b> <a href='{AUTHOR_LINK}'>{AUTHOR_USERNAME}</a>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Admin bilan bog'lanish", url=AUTHOR_LINK)],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_start")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except:
        await safe_send_message(callback.from_user.id, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "list_all")
async def list_all_start(callback: CallbackQuery):
    await update_user_activity(callback.from_user.id)
    
    anime_rows = await db.fetch_all("SELECT name, code, total_parts, status FROM media WHERE type = 'anime' ORDER BY name")
    drama_rows = await db.fetch_all("SELECT name, code, total_parts, status FROM media WHERE type = 'drama' ORDER BY name")
    
    anime_list = list(anime_rows) if anime_rows else []
    drama_list = list(drama_rows) if drama_rows else []
    
    if anime_list:
        anime_text = "🎬 ANIMELAR RO'YXATI\n\n"
        for i, an in enumerate(anime_list, 1):
            name = an[0] if isinstance(an, tuple) else an['name']
            code = an[1] if isinstance(an, tuple) else an['code']
            parts = an[2] if isinstance(an, tuple) else an['total_parts']
            status = an[3] if isinstance(an, tuple) else an['status']
            status_emoji = "🟢" if status == "ongoing" else "✅" if status == "completed" else "⏸"
            anime_text += f"{i}. {name}\n   Kod: {code} | Qism: {parts} | {status_emoji}\n\n"
        file = io.BytesIO(anime_text.encode('utf-8'))
        document = BufferedInputFile(file.getvalue(), filename="Animelar_Royxati.txt")
        await bot.send_document(callback.from_user.id, document)
    
    if drama_list:
        drama_text = "🎭 DRAMALAR RO'YXATI\n\n"
        for i, dr in enumerate(drama_list, 1):
            name = dr[0] if isinstance(dr, tuple) else dr['name']
            code = dr[1] if isinstance(dr, tuple) else dr['code']
            parts = dr[2] if isinstance(dr, tuple) else dr['total_parts']
            status = dr[3] if isinstance(dr, tuple) else dr['status']
            status_emoji = "🟢" if status == "ongoing" else "✅" if status == "completed" else "⏸"
            drama_text += f"{i}. {name}\n   Kod: {code} | Qism: {parts} | {status_emoji}\n\n"
        file = io.BytesIO(drama_text.encode('utf-8'))
        document = BufferedInputFile(file.getvalue(), filename="Dramalar_Royxati.txt")
        await bot.send_document(callback.from_user.id, document)
    
    if not anime_list and not drama_list:
        try:
            await callback.message.edit_text("📭 Hozircha media mavjud emas!", parse_mode="HTML")
        except:
            await safe_send_message(callback.from_user.id, "📭 Hozircha media mavjud emas!", parse_mode="HTML")
    
    await callback.answer()

@dp.callback_query(F.data.startswith("view_media_"))
async def view_media(callback: CallbackQuery):
    media_id = int(callback.data.split("_")[2])
    media_row = await db.fetch_one("SELECT id, name, code, total_parts, status, season, genre, voice, sponsor, quality, image_url FROM media WHERE id = ?", (media_id,))
    
    if not media_row:
        await callback.answer("Media topilmadi!")
        return
    
    name = media_row[1] if isinstance(media_row, tuple) else media_row['name']
    code = media_row[2] if isinstance(media_row, tuple) else media_row['code']
    total_parts = media_row[3] if isinstance(media_row, tuple) else media_row['total_parts']
    status = media_row[4] if isinstance(media_row, tuple) else media_row['status']
    season = media_row[5] if isinstance(media_row, tuple) else media_row['season']
    genre = media_row[6] if isinstance(media_row, tuple) else media_row['genre']
    voice = media_row[7] if isinstance(media_row, tuple) else media_row['voice']
    sponsor = media_row[8] if isinstance(media_row, tuple) else media_row['sponsor']
    quality = media_row[9] if isinstance(media_row, tuple) else media_row['quality']
    image = media_row[10] if isinstance(media_row, tuple) else media_row['image_url']
    
    status_text = {"ongoing": "🟢 Davom etmoqda", "completed": "✅ Tugallangan", "hiatus": "⏸ To'xtatilgan"}.get(status, "Noma'lum")
    voice_text = voice if voice else f"{AUTHOR_USERNAME}"
    sponsor_text = sponsor if sponsor else "AniCity Rasmiy"
    
    text = f"""
┌─────────────────────────────────
🎬 <b>{name}</b>
└─────────────────────────────────

┌─────────────────────────────────
• Janr: {genre}
• Sezon: {season}
• Qism: {total_parts} ta
• Holati: {status_text}
• Ovoz: {voice_text}
• Himoy: {sponsor_text}
• Sifat: {quality}
└─────────────────────────────────

🔢 Kod: <code>{code}</code>
📢 Kanal: @AniCity_Rasmiy
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📺 Tomosha qilish", callback_data=f"watch_parts_{media_id}")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="back_to_start")]
    ])
    
    if image:
        await safe_send_photo(callback.from_user.id, photo=image, caption=text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await safe_send_message(callback.from_user.id, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("watch_parts_"))
async def watch_parts(callback: CallbackQuery):
    media_id = int(callback.data.split("_")[2])
    media_row = await db.fetch_one("SELECT name FROM media WHERE id = ?", (media_id,))
    if not media_row:
        await callback.answer("Media topilmadi!")
        return
    
    media_name = media_row[0] if isinstance(media_row, tuple) else media_row['name']
    
    parts_rows = await db.fetch_all("SELECT part_number FROM parts WHERE media_id = ? ORDER BY part_number", (media_id,))
    parts_list = list(parts_rows) if parts_rows else []
    
    if not parts_list:
        await callback.answer("Hozircha qismlar mavjud emas!")
        return
    
    builder = InlineKeyboardBuilder()
    for part in parts_list:
        part_num = part[0] if isinstance(part, tuple) else part['part_number']
        builder.button(text=f"{part_num}", callback_data=f"watch_part_{media_id}_{part_num}")
    builder.adjust(5)
    builder.row(InlineKeyboardButton(text="🔙 Ortga", callback_data="back_to_start"))
    
    await callback.message.edit_text(f"📺 <b>{media_name}</b>\n\n📹 Qismlarni tanlang:", reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("watch_part_"))
async def watch_part(callback: CallbackQuery):
    parts = callback.data.split("_")
    media_id = int(parts[2])
    part_num = int(parts[3])
    
    part_row = await db.fetch_one("SELECT file_id, caption FROM parts WHERE media_id = ? AND part_number = ?", (media_id, part_num))
    if not part_row:
        await callback.answer("Qism topilmadi!")
        return
    
    file_id = part_row[0] if isinstance(part_row, tuple) else part_row['file_id']
    caption = part_row[1] if isinstance(part_row, tuple) else part_row['caption']
    
    media_row = await db.fetch_one("SELECT name FROM media WHERE id = ?", (media_id,))
    media_name = media_row[0] if media_row else "Anime"
    
    full_caption = f"🎬 {media_name}\n📹 {part_num}-qism\n\n{caption if caption else ''}"
    await safe_send_video(callback.from_user.id, video=file_id, caption=full_caption, parse_mode="HTML")
    await callback.answer()

# ================= BOTNI ISHGA TUSHIRISH =================
async def main():
    print("=" * 60)
    print("🤖 ANICITY RASMIY BOT - TUZATILGAN VERSIYA")
    print("=" * 60)
    print(f"🚀 BOT START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"👑 Adminlar: {ADMINS}")
    print(f"📢 Asosiy kanal: {MAIN_CHANNEL}")
    print(f"👨‍💻 Muallif: {AUTHOR_USERNAME}")
    print("=" * 60)
    
    await db.connect()
    print("✅ Database ulandi!")
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook o'chirildi!")
    except Exception as e:
        print(f"⚠️ Webhook xatosi: {e}")
    
    print("✅ Bot to'liq ishga tushdi!")
    print(f"⏰ Ishga tushgan vaqt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n⚠️ Bot to'xtatildi!")
    except Exception as e:
        print(f"❌ Bot xatosi: {e}")
    finally:
        await db.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
