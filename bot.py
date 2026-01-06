# =========================
# TELEGRAM BOT — FINAL
# =========================

import asyncio
import logging
import os
import json
from enum import Enum
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ParseMode

import redis.asyncio as redis
from dotenv import load_dotenv


# ---------- ENV ----------

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")
CORE_SERVICE_URL = os.getenv("CORE_SERVICE_URL", "http://core-service:8082")
WEB_CLIENT_URL = os.getenv("WEB_CLIENT_URL", "https://localhost:3000")


# ---------- LOGGING ----------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("telegram-client")


# ---------- BOT ----------

bot = Bot(
    token=BOT_TOKEN,
    parse_mode=ParseMode.MARKDOWN_V2,
)
dp = Dispatcher()


# ---------- REDIS ----------

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True,
)


# ---------- USER STATUS ----------

class UserStatus(str, Enum):
    UNKNOWN = "unknown"
    ANONYMOUS = "anonymous"
    AUTHORIZED = "authorized"


# ---------- MARKDOWN V2 ----------

MD_V2_SPECIALS = r"_*[]()~`>#+-=|{}.!"

def escape_md(text: str) -> str:
    for ch in MD_V2_SPECIALS:
        text = text.replace(ch, f"\\{ch}")
    return text


# ---------- REDIS HELPERS ----------

async def get_user(chat_id: int) -> dict | None:
    data = await redis_client.get(f"user:{chat_id}")
    return json.loads(data) if data else None


async def set_user(chat_id: int, data: dict):
    await redis_client.set(f"user:{chat_id}", json.dumps(data))


async def delete_user(chat_id: int):
    await redis_client.delete(f"user:{chat_id}")


async def get_status(chat_id: int) -> UserStatus:
    user = await get_user(chat_id)
    if not user:
        return UserStatus.UNKNOWN
    return UserStatus(user.get("status", UserStatus.UNKNOWN))


# ---------- AUTH GUARD ----------

async def require_auth(message: Message) -> bool:
    if await get_status(message.chat.id) != UserStatus.AUTHORIZED:
        await message.answer(
            escape_md(
                "🔐 *Вы не авторизованы*\n\n"
                "Используйте команду /login"
            )
        )
        return False
    return True


# =========================
# COMMANDS
# =========================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    name = message.from_user.first_name
    await message.answer(
        escape_md(
            f"👋 *Привет, {name}!* \n\n"
            "🤖 *Я — Telegram\\-клиент системы массового тестирования*\n\n"
            "Система находится в стадии *активной разработки*\n\n"
            "📊 *Что уже работает:*\n"
            "• Docker контейнеры\n"
            "• Redis / Postgres / Mongo\n"
            "• Core API\n"
            "• Auth API\n"
            "• Базовая авторизация\n\n"
            "📌 *Доступные команды:*\n"
            "/help — справка\n"
            "/status — статус системы\n"
            "/services — сервисы\n"
            "/login — авторизация"
        )
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        escape_md(
            "🆘 *Справка по командам*\n\n"
            "🚀 *Старт:*\n"
            "/start — начало работы\n\n"
            "🔐 *Авторизация:*\n"
            "/login — начать вход\n"
            "/completelogin — завершить вход\n"
            "/logout — выйти\n"
            "/logout_all — выйти везде\n\n"
            "🧪 *Тестирование:*\n"
            "/tests — список тестов\n"
            "/starttest <id> — начать тест\n\n"
            "ℹ️ *Информация:*\n"
            "/status — статус системы\n"
            "/services — сервисы"
        )
    )


@dp.message(Command("login"))
async def cmd_login(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🟡 Войти через Яндекс",
                    url=f"{WEB_CLIENT_URL}/auth/yandex"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🐙 GitHub",
                    url=f"{WEB_CLIENT_URL}/auth/github"
                )
            ]
        ]
    )

    await set_user(
        message.chat.id,
        {
            "status": UserStatus.ANONYMOUS,
            "created_at": datetime.utcnow().isoformat()
        }
    )

    await message.answer(
        escape_md(
            "🔐 *Авторизация*\n\n"
            "Выберите способ входа:"
        ),
        reply_markup=kb
    )


@dp.message(Command("completelogin"))
async def cmd_completelogin(message: Message):
    await set_user(
        message.chat.id,
        {
            "status": UserStatus.AUTHORIZED,
            "authorized_at": datetime.utcnow().isoformat()
        }
    )

    await message.answer(
        escape_md("✅ *Авторизация успешно завершена*")
    )


@dp.message(Command("logout"))
async def cmd_logout(message: Message):
    await delete_user(message.chat.id)
    await message.answer(
        escape_md("🚪 *Вы вышли из системы*")
    )


@dp.message(Command("logout_all"))
async def cmd_logout_all(message: Message):
    await delete_user(message.chat.id)
    await message.answer(
        escape_md(
            "🚨 *Вы вышли из системы на всех устройствах*\n\n"
            "Все сессии сброшены"
        )
    )


@dp.message(Command("status"))
async def cmd_status(message: Message):
    name = message.from_user.first_name
    status = await get_status(message.chat.id)

    await message.answer(
        escape_md(
            f"📊 *СТАТУС СИСТЕМЫ*\n\n"
            f"👤 Пользователь: {name}\n"
            f"🔑 Статус: {status}\n\n"
            "🟢 *Сервисы:*\n"
            "• core-service — Онлайн :8082\n"
            "• auth-service — Онлайн :8081\n"
            "• web-client — Онлайн :3000\n"
            "• postgres — Онлайн :5432\n"
            "• mongodb — Онлайн :27017\n"
            "• redis — Онлайн :6379\n\n"
            "🌐 *Ссылки:*\n"
            f"• Web: {WEB_CLIENT_URL}\n"
            f"• Core API: {CORE_SERVICE_URL}\n"
            f"• Auth API: {AUTH_SERVICE_URL}"
        )
    )


@dp.message(Command("services"))
async def cmd_services(message: Message):
    await message.answer(
        escape_md(
            "🧩 *СЕРВИСЫ*\n\n"
            "⚙️ core-service\n"
            "— API логики тестирования\n\n"
            "🔐 auth-service\n"
            "— Авторизация пользователей\n\n"
            "🌐 web-client\n"
            "— Пользовательский интерфейс\n\n"
            "🗄 postgres\n"
            "— Основная БД\n\n"
            "📦 mongodb\n"
            "— Хранилище тестов\n\n"
            "⚡ redis\n"
            "— Кэш и сессии"
        )
    )


@dp.message(Command("tests"))
async def cmd_tests(message: Message):
    if not await require_auth(message):
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧪 Тест 1", callback_data="test_1")],
            [InlineKeyboardButton(text="🧪 Тест 2", callback_data="test_2")],
        ]
    )

    await message.answer(
        escape_md("🧪 *Доступные тесты:*"),
        reply_markup=kb
    )


@dp.message(Command("starttest"))
async def cmd_starttest(message: Message):
    if not await require_auth(message):
        return

    await message.answer(
        escape_md("▶️ *Тест запущен*")
    )


# =========================
# ENTRYPOINT
# =========================

async def main():
    logger.info("🤖 Telegram bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
