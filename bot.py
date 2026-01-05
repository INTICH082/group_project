import os
import time
import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv
import redis.asyncio as redis

# =========================
# INIT
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True
)

# =========================
# REDIS HELPERS
# =========================

def rkey(chat_id: int) -> str:
    return f"user:{chat_id}"

async def get_user(chat_id: int) -> dict:
    return await redis_client.hgetall(rkey(chat_id))

async def set_user(chat_id: int, data: dict):
    await redis_client.hset(rkey(chat_id), mapping=data)

async def delete_user(chat_id: int):
    await redis_client.delete(rkey(chat_id))

# =========================
# AUTH CHECK
# =========================

async def require_auth(message: types.Message) -> bool:
    user = await get_user(message.chat.id)

    if not user or user.get("status") != "AUTHORIZED":
        await message.answer(
            "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
            "Для выполнения команды необходимо авторизоваться.\n\n"
            "🔐 Используйте команду:\n"
            "/login"
        )
        return False

    return True

# =========================
# COMMANDS
# =========================

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    await message.answer(
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        "🤖 Я — бот системы тестирования.\n"
        "Система находится в стадии активной разработки.\n\n"
        "📊 <b>Что уже работает:</b>\n"
        "• Docker контейнеры\n"
        "• Базы данных\n"
        "• Web-интерфейс\n"
        "• API-сервисы\n"
        "• Базовая авторизация\n\n"
        "🧩 <b>Основные команды:</b>\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/help — помощь\n"
        "/login — авторизация\n"
        "/complete_login — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test — начать тест\n\n"
        "🌐 <b>Ссылки:</b>\n"
        "• Web: http://localhost:3000\n"
        "• Core API: http://core-service:8082\n"
        "• Auth API: http://auth-service:8081"
    )

@dp.message_handler(commands=["help"])
async def help_cmd(message: types.Message):
    await message.answer(
        "🆘 <b>ПОМОЩЬ</b>\n\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/login — авторизация\n"
        "/complete_login — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test — начать тест"
    )

@dp.message_handler(commands=["status"])
async def status_cmd(message: types.Message):
    await message.answer(
        "📊 <b>СТАТУС СИСТЕМЫ</b>\n\n"
        "Все сервисы работают 🟢"
    )

@dp.message_handler(commands=["services"])
async def services_cmd(message: types.Message):
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

@dp.message_handler(commands=["login"])
async def login_cmd(message: types.Message):
    user = await get_user(message.chat.id)

    if user and user.get("status") == "AUTHORIZED":
        await message.answer(
            "✅ <b>ВЫ УЖЕ АВТОРИЗОВАНЫ</b>\n\n"
            "Дополнительных действий не требуется."
        )
        return

    code = str(int(time.time()))

    await set_user(message.chat.id, {
        "status": "ANONYMOUS",
        "login_code": code
    })

    await message.answer(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        f"Ваш код: <code>{code}</code>\n\n"
        "Введите код в веб-клиенте и затем выполните:\n"
        "/complete_login"
    )

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(message: types.Message):
    user = await get_user(message.chat.id)

    if not user or user.get("status") != "ANONYMOUS":
        await message.answer(
            "❌ <b>СЕССИЯ НЕ НАЙДЕНА</b>\n\n"
            "Выполните /login и попробуйте снова."
        )
        return

    await message.answer(
        "⏳ <b>ОЖИДАНИЕ ПОДТВЕРЖДЕНИЯ</b>\n\n"
        "Завершите вход в веб-клиенте."
    )

@dp.message_handler(commands=["tests"])
async def tests_cmd(message: types.Message):
    if not await require_auth(message):
        return

    await message.answer(
        "🧪 <b>ТЕСТОВ НЕТ</b>\n\n"
        "В данный момент доступных тестов нет."
    )

@dp.message_handler(commands=["start_test"])
async def start_test_cmd(message: types.Message):
    if not await require_auth(message):
        return

    await message.answer(
        "🚀 <b>ТЕСТ НЕ ДОСТУПЕН</b>\n\n"
        "Сначала выберите тест через /tests."
    )

@dp.message_handler()
async def unknown_cmd(message: types.Message):
    await message.answer(
        "❓ <b>Неизвестная команда</b>\n\n"
        "Используйте /help"
    )

# =========================
# RUN
# =========================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
