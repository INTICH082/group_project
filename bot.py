import asyncio
import os
import time
from enum import Enum

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv
import redis.asyncio as redis

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")

bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()
router = Router()
dp.include_router(router)

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# =========================
# MODELS
# =========================

class UserStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    ANONYMOUS = "ANONYMOUS"
    AUTHORIZED = "AUTHORIZED"


def redis_key(chat_id: int) -> str:
    return f"user:{chat_id}"


async def get_user(chat_id: int) -> dict | None:
    return await redis_client.hgetall(redis_key(chat_id))


async def set_user(chat_id: int, data: dict):
    await redis_client.hset(redis_key(chat_id), mapping=data)


async def delete_user(chat_id: int):
    await redis_client.delete(redis_key(chat_id))


# =========================
# HELPERS
# =========================

async def require_auth(message: Message) -> bool:
    user = await get_user(message.chat.id)
    if not user or user.get("status") != UserStatus.AUTHORIZED:
        await message.answer(
            "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
            "Для выполнения команды необходимо авторизоваться.\n\n"
            "🔐 Используйте команду:\n"
            "<code>/login</code>"
        )
        return False
    return True


# =========================
# COMMANDS
# =========================

@router.message(Command("start"))
async def start(message: Message):
    await message.answer(
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        "🤖 Я — бот системы тестирования.\n"
        "Система находится в стадии активной разработки.\n\n"
        "📊 <b>Что уже работает:</b>\n"
        "• Docker-контейнеры\n"
        "• Базы данных\n"
        "• API сервисы\n"
        "• Базовая авторизация\n\n"
        "🧭 <b>Основные команды:</b>\n"
        "/start — Главное меню\n"
        "/status — Статус системы\n"
        "/services — Сервисы\n"
        "/help — Помощь\n"
        "/login — Авторизация\n"
        "/complete_login — Завершить авторизацию\n"
        "/tests — Список тестов\n"
        "/start_test — Начать тест\n\n"
        "🌐 <b>Ссылки:</b>\n"
        "• Web: http://localhost:3000\n"
        "• API Core: http://core-service:8082\n"
        "• API Auth: http://auth-service:8081"
    )


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "🆘 <b>ПОМОЩЬ</b>\n\n"
        "/start — Главное меню\n"
        "/status — Статус системы\n"
        "/services — Сервисы\n"
        "/login — Авторизация\n"
        "/complete_login — Завершить авторизацию\n"
        "/tests — Список тестов\n"
        "/start_test — Начать тест"
    )


@router.message(Command("services"))
async def services(message: Message):
    await message.answer(
        "🛠 <b>СЕРВИСЫ СИСТЕМЫ</b>\n\n"
        "<b>CORE-SERVICE</b>\n"
        "Статус: 🟢 Онлайн\n"
        "Порт: 8082\n\n"
        "<b>AUTH-SERVICE</b>\n"
        "Статус: 🟢 Онлайн\n"
        "Порт: 8081\n\n"
        "<b>WEB-CLIENT</b>\n"
        "Статус: 🟢 Онлайн\n"
        "Порт: 3000\n\n"
        "POSTGRES — 5432\n"
        "MONGODB — 27017\n"
        "REDIS — 6379"
    )


@router.message(Command("login"))
async def login(message: Message):
    user = await get_user(message.chat.id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await message.answer(
            "✅ <b>ВЫ УЖЕ АВТОРИЗОВАНЫ</b>\n\n"
            "Дополнительных действий не требуется."
        )
        return

    login_token = f"LOGIN-{int(time.time())}"

    await set_user(message.chat.id, {
        "status": UserStatus.ANONYMOUS,
        "login_token": login_token,
        "created_at": int(time.time())
    })

    await message.answer(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        f"Ваш код: <code>{login_token}</code>\n\n"
        "Введите код в веб-клиенте и затем выполните:\n"
        "<code>/complete_login</code>"
    )


@router.message(Command("complete_login"))
async def complete_login(message: Message):
    user = await get_user(message.chat.id)

    if not user or user.get("status") != UserStatus.ANONYMOUS:
        await message.answer(
            "❌ <b>СЕССИЯ НЕ НАЙДЕНА</b>\n\n"
            "Выполните /login и попробуйте снова."
        )
        return

    # ❗ Здесь должен быть реальный запрос в Auth Service
    await message.answer(
        "⏳ <b>ОЖИДАНИЕ ПОДТВЕРЖДЕНИЯ</b>\n\n"
        "Завершите вход в веб-клиенте."
    )


@router.message(Command("tests"))
async def tests(message: Message):
    if not await require_auth(message):
        return

    await message.answer(
        "🧪 <b>ТЕСТОВ НЕТ</b>\n\n"
        "В данный момент доступных тестов нет."
    )


@router.message(Command("start_test"))
async def start_test(message: Message):
    if not await require_auth(message):
        return

    await message.answer(
        "🚀 <b>НЕТ ДОСТУПНЫХ ТЕСТОВ</b>\n\n"
        "Сначала выберите тест через /tests."
    )


# =========================
# FALLBACK
# =========================

@router.message()
async def unknown(message: Message):
    await message.answer(
        "❓ <b>Неизвестная команда</b>\n\n"
        "Используйте /help"
    )


# =========================
# ENTRYPOINT
# =========================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
