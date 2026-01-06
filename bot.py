import asyncio
import logging
import os
from enum import Enum
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
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

WEB_CLIENT_URL = os.getenv("WEB_CLIENT_URL", "http://localhost:3000")
CORE_SERVICE_URL = os.getenv("CORE_SERVICE_URL", "http://core-service:8082")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("telegram-client")

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
# MARKDOWN V2 SAFE
# =========================

MD_V2_SPECIALS = r"_*[]()~`>#+-=|{}.!"

def md(text: str) -> str:
    for ch in MD_V2_SPECIALS:
        text = text.replace(ch, f"\\{ch}")
    return text

# =========================
# REDIS HELPERS
# =========================

async def get_user(chat_id: int) -> dict | None:
    data = await redis_client.get(f"user:{chat_id}")
    return eval(data) if data else None

async def set_user(chat_id: int, data: dict):
    await redis_client.set(f"user:{chat_id}", str(data))

async def delete_user(chat_id: int):
    await redis_client.delete(f"user:{chat_id}")

async def get_status(chat_id: int) -> UserStatus:
    user = await get_user(chat_id)
    if not user:
        return UserStatus.UNKNOWN
    return UserStatus(user.get("status", UserStatus.UNKNOWN))

# =========================
# AUTH GUARD
# =========================

async def require_auth(message: Message) -> bool:
    status = await get_status(message.chat.id)
    if status != UserStatus.AUTHORIZED:
        await message.answer(
            md(
                "🔐 Вы не авторизованы\n\n"
                "Используйте команду /login"
            )
        )
        return False
    return True

# =========================
# KEYBOARDS
# =========================

def auth_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🐙 GitHub", callback_data="login:github"),
                InlineKeyboardButton(text="🟡 Яндекс ID", callback_data="login:yandex"),
            ],
            [
                InlineKeyboardButton(text="🔢 Код", callback_data="login:code"),
            ],
        ]
    )

# =========================
# COMMANDS
# =========================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    text = f"""
👋 Привет

🤖 Telegram клиент системы массового тестирования
Система находится в стадии активной разработки

📊 Что уже работает
• Docker контейнеры
• Redis Postgres Mongo
• Core API
• Auth API
• Базовая авторизация

🛠 Что будет добавлено
• Прохождение тестов
• Уведомления

📌 Основные команды
/start
/help
/status
/services

🔐 Авторизация
/login
/completelogin
/logout

🧪 Тестирование
/tests
/starttest <id>

🌐 Ссылки
Web {WEB_CLIENT_URL}
Core {CORE_SERVICE_URL}
Auth {AUTH_SERVICE_URL}
"""
    await message.answer(md(text))

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        md(
            "🆘 Справка\n\n"
            "/start — начало работы\n"
            "/status — статус системы\n"
            "/services — сервисы\n\n"
            "/login — вход\n"
            "/completelogin — завершить вход\n"
            "/logout — выход\n\n"
            "/tests — список тестов\n"
            "/starttest <id> — начать тест"
        )
    )

@dp.message(Command("login"))
async def cmd_login(message: Message):
    status = await get_status(message.chat.id)
    if status == UserStatus.AUTHORIZED:
        await message.answer(md("✅ Вы уже авторизованы"))
        return

    await message.answer(
        md("🔐 Авторизация\n\nВыберите способ входа"),
        reply_markup=auth_keyboard(),
    )

@dp.message(Command("completelogin"))
async def cmd_complete_login(message: Message):
    status = await get_status(message.chat.id)
    if status == UserStatus.AUTHORIZED:
        await message.answer(md("✅ Вы уже авторизованы"))
        return

    await set_user(
        message.chat.id,
        {
            "status": UserStatus.AUTHORIZED,
            "authorized_at": datetime.utcnow().isoformat(),
        },
    )

    await message.answer(
        md(
            "🎉 Авторизация завершена\n\n"
            "Теперь вам доступны тесты и сервисы"
        )
    )

@dp.message(Command("logout"))
async def cmd_logout(message: Message):
    status = await get_status(message.chat.id)

    if status != UserStatus.AUTHORIZED:
        await message.answer(
            md(
                "ℹ️ Вы не авторизованы\n\n"
                "Выход из системы невозможен"
            )
        )
        return

    await delete_user(message.chat.id)
    await message.answer(md("🔓 Вы успешно вышли из системы"))

@dp.message(Command("status"))
async def cmd_status(message: Message):
    status = await get_status(message.chat.id)

    await message.answer(
        md(
            f"📊 Статус системы\n\n"
            f"Пользователь {status}\n"
            f"Время {datetime.now().strftime('%H:%M:%S')}\n\n"
            "Все сервисы онлайн"
        )
    )

@dp.message(Command("services"))
async def cmd_services(message: Message):
    await message.answer(
        md(
            "🧩 Сервисы\n\n"
            "core service\n"
            "auth service\n"
            "web client\n"
            "postgres\n"
            "mongodb\n"
            "redis"
        )
    )

# =========================
# TESTS
# =========================

TESTS = [
    {"id": "python", "title": "Python основы"},
    {"id": "docker", "title": "Docker основы"},
    {"id": "backend", "title": "Backend Junior"},
]

@dp.message(Command("tests"))
async def cmd_tests(message: Message):
    if not await require_auth(message):
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["title"], callback_data=f"test:{t['id']}")]
            for t in TESTS
        ]
    )

    await message.answer(
        md("🧪 Доступные тесты"),
        reply_markup=kb,
    )

@dp.callback_query(lambda c: c.data.startswith("test:"))
async def test_callback(call: CallbackQuery):
    test_id = call.data.split(":")[1]
    test = next((t for t in TESTS if t["id"] == test_id), None)

    if not test:
        await call.answer("Тест не найден", show_alert=True)
        return

    await call.message.answer(
        md(
            f"🚀 Тест запущен\n\n"
            f"Название {test['title']}\n\n"
            "Логика будет добавлена позже"
        )
    )
    await call.answer()

# =========================
# AUTH CALLBACK
# =========================

@dp.callback_query(lambda c: c.data.startswith("login:"))
async def auth_callback(call: CallbackQuery):
    method = call.data.split(":")[1]

    await set_user(
        call.message.chat.id,
        {
            "status": UserStatus.ANONYMOUS,
            "auth_method": method,
            "created_at": datetime.utcnow().isoformat(),
        },
    )

    await call.message.answer(
        md(
            "🔐 Авторизация начата\n\n"
            f"Перейдите в Web {WEB_CLIENT_URL}"
        )
    )
    await call.answer()

# =========================
# MAIN
# =========================

async def main():
    logger.info("🤖 Telegram bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
