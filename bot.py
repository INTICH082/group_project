import asyncio
import logging
import os
import json
import re
from enum import Enum
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ParseMode

import redis.asyncio as redis
from dotenv import load_dotenv

# =========================
# ENV
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "")
CORE_SERVICE_URL = os.getenv("CORE_SERVICE_URL", "")
WEB_CLIENT_URL = os.getenv("WEB_CLIENT_URL", "https://localhost:3000")

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("telegram-client")

# =========================
# MARKDOWN V2 SAFE
# =========================

def md(text: str) -> str:
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)

# =========================
# BOT
# =========================

bot = Bot(
    token=BOT_TOKEN,
    parse_mode=ParseMode.MARKDOWN_V2,
)

dp = Dispatcher()

# =========================
# REDIS
# =========================

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True,
)

# =========================
# USER STATUS
# =========================

class UserStatus(str, Enum):
    UNKNOWN = "unknown"
    ANONYMOUS = "anonymous"
    AUTHORIZED = "authorized"

# =========================
# REDIS HELPERS
# =========================

async def get_user(chat_id: int):
    data = await redis_client.get(f"user:{chat_id}")
    return json.loads(data) if data else None

async def set_user(chat_id: int, data: dict):
    await redis_client.set(f"user:{chat_id}", json.dumps(data))

async def delete_user(chat_id: int):
    await redis_client.delete(f"user:{chat_id}")

async def get_status(chat_id: int) -> UserStatus:
    user = await get_user(chat_id)
    return UserStatus(user["status"]) if user else UserStatus.UNKNOWN

# =========================
# AUTH GUARD
# =========================

async def require_auth(message: Message) -> bool:
    user = await get_user(message.chat.id)

    if not user:
        await message.answer(md("❌ *Вы не авторизованы*"))
        return False

    if user.get("status") != UserStatus.AUTHORIZED:
        await message.answer(md("⏳ *Ожидание завершения авторизации*"))
        return False

    return True

# =========================
# STUB TESTS
# =========================

async def get_user_tests(chat_id: int):
    return [
        {"id": 1, "name": "Python Basics", "passed": False, "score": 0},
        {"id": 2, "name": "Async IO", "passed": True, "score": 8},
    ]

# =========================
# COMMANDS
# =========================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    name = message.from_user.first_name or "пользователь"

    text = f"""
👋 *Добро пожаловать, {name}*

🤖 *Telegram\\-клиент системы массового тестирования*

━━━━━━━━━━━━━━━━━━
📊 *Текущий статус проекта*
━━━━━━━━━━━━━━━━━━
🟢 Docker\\-инфраструктура  
🟢 Core API  
🟢 Auth API  
🟢 Web\\-клиент  
🟢 Redis / Postgres / Mongo  

━━━━━━━━━━━━━━━━━━
📌 *Основные команды*
━━━━━━━━━━━━━━━━━━
/start — старт  
/help — справка  
/status — статус  
/services — сервисы  

━━━━━━━━━━━━━━━━━━
🧪 *Тестирование*
━━━━━━━━━━━━━━━━━━
/tests — список тестов  
/starttest — начать тест  

━━━━━━━━━━━━━━━━━━
🌐 *Ссылки*
━━━━━━━━━━━━━━━━━━
Web: {WEB_CLIENT_URL}
"""

    await message.answer(md(text))

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(md("""
🆘 *Справка по командам*

━━━━━━━━━━━━━━━━━━
🚀 *Начало*
━━━━━━━━━━━━━━━━━━
/start — старт работы  
/help — эта справка  

━━━━━━━━━━━━━━━━━━
🔐 *Авторизация*
━━━━━━━━━━━━━━━━━━
/login — вход  
/completelogin — завершить вход  
/logout — выход  

━━━━━━━━━━━━━━━━━━
🧪 *Тестирование*
━━━━━━━━━━━━━━━━━━
/tests — список тестов  
/starttest — начать тест  

━━━━━━━━━━━━━━━━━━
ℹ️ *Информация*
━━━━━━━━━━━━━━━━━━
/status — статус  
/services — сервисы
"""))

@dp.message(Command("login"))
async def cmd_login(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 GitHub (заглушка)", callback_data="login_stub_github")],
        [InlineKeyboardButton(text="🟡 Яндекс (заглушка)", callback_data="login_stub_yandex")],
        [InlineKeyboardButton(text="🔢 Ввести код", callback_data="login_code")],
    ])

    await message.answer(
        md("🔐 *Авторизация*\n\nВыберите способ входа:"),
        reply_markup=kb,
    )

@dp.message(Command("completelogin"))
async def cmd_completelogin(message: Message):
    await set_user(
        message.chat.id,
        {
            "status": UserStatus.AUTHORIZED,
            "authorized_at": datetime.utcnow().isoformat(),
        },
    )

    await message.answer(md("✅ *Авторизация успешно завершена*"))

@dp.message(Command("logout"))
async def cmd_logout(message: Message):
    if not await require_auth(message):
        return

    await delete_user(message.chat.id)
    await message.answer(md("🚪 *Вы вышли из системы*"))

@dp.message(Command("status"))
async def cmd_status(message: Message):
    status = await get_status(message.chat.id)

    await message.answer(md(f"""
📊 *Статус системы*

━━━━━━━━━━━━━━━━━━
👤 Пользователь: {message.from_user.first_name}
🔐 Статус: {status}

━━━━━━━━━━━━━━━━━━
🟢 *Сервисы*
━━━━━━━━━━━━━━━━━━
• core\\-service — онлайн  
• auth\\-service — онлайн  
• web\\-client — онлайн  
• postgres — онлайн  
• mongodb — онлайн  
• redis — онлайн
"""))

@dp.message(Command("services"))
async def cmd_services(message: Message):
    await message.answer(md("""
🧩 *Сервисы системы*

━━━━━━━━━━━━━━━━━━
⚙ *core\\-service*
API логики тестирования

🔐 *auth\\-service*
Авторизация пользователей

🌐 *web\\-client*
Пользовательский интерфейс

🗄 *postgres*
Основная база данных

📦 *mongodb*
Хранилище тестов

⚡ *redis*
Кэш и сессии
"""))

# =========================
# MAIN
# =========================

async def main():
    logger.info("🤖 Telegram bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
