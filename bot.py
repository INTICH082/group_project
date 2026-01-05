import asyncio
import os
import time

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message
from aiogram.filters import Command
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
dp = Dispatcher()
router = Router()

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# =========================
# REDIS HELPERS
# =========================

def rkey(chat_id: int) -> str:
    return f"user:{chat_id}"

async def get_user(chat_id: int) -> dict:
    return await redis_client.hgetall(rkey(chat_id))

async def set_user(chat_id: int, data: dict):
    await redis_client.hset(rkey(chat_id), mapping=data)

# ========================
# AUTH CHECK
# =========================

async def require_auth(message: Message) -> bool:
    user = await get_user(message.chat.id)
    if not user or user.get("status") != "AUTHORIZED":
        await message.answer(
            "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
            "Для выполнения команды необходимо авторизоваться.\n\n"
            "🔐 Используйте команду:\n/login"
        )
        return False
    return True

# =========================
# COMMANDS
# =========================

@router.message(Command("start"))
async def start_cmd(message: Message):
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

@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "🆘 <b>ПОМОЩЬ</b>\n\n"
        "/start\n/status\n/services\n/login\n/complete_login\n/tests\n/start_test"
    )

@router.message(Command("status"))
async def status_cmd(message: Message):
    await message.answer("📊 <b>СТАТУС СИСТЕМЫ</b>\n\nВсе сервисы работают 🟢")

@router.message(Command("services"))
async def services_cmd(message: Message):
    await message.answer(
        "🛠 <b>СЕРВИСЫ СИСТЕМЫ</b>\n\n"
        "<b>CORE-SERVICE</b>\n🟢 Онлайн — 8082\n\n"
        "<b>AUTH-SERVICE</b>\n🟢 Онлайн — 8081\n\n"
        "<b>WEB-CLIENT</b>\n🟢 Онлайн — 3000\n\n"
        "POSTGRES — 5432\n"
        "MONGODB — 27017\n"
        "REDIS — 6379"
    )

@router.message(Command("login"))
async def login_cmd(message: Message):
    user = await get_user(message.chat.id)

    if user.get("status") == "AUTHORIZED":
        await message.answer("✅ <b>Вы уже авторизованы</b>")
        return

    code = str(int(time.time()))
    await set_user(message.chat.id, {
        "status": "ANONYMOUS",
        "login_code": code
    })

    await message.answer(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        f"Ваш код: <code>{code}</code>\n\n"
        "Введите код в веб-клиенте и выполните:\n/complete_login"
    )

@router.message(Command("complete_login"))
async def complete_login_cmd(message: Message):
    user = await get_user(message.chat.id)

    if user.get("status") != "ANONYMOUS":
        await message.answer("❌ <b>Сессия не найдена</b>\n\nИспользуйте /login")
        return

    await message.answer("⏳ <b>Ожидание подтверждения в веб-клиенте</b>")

@router.message(Command("tests"))
async def tests_cmd(message: Message):
    if not await require_auth(message):
        return

    await message.answer("🧪 <b>Тестов нет</b>")

@router.message(Command("start_test"))
async def start_test_cmd(message: Message):
    if not await require_auth(message):
        return

    await message.answer("🚀 <b>Выберите тест через /tests</b>")

@router.message(F.text)
async def unknown_cmd(message: Message):
    await message.answer("❓ <b>Неизвестная команда</b>\nИспользуйте /help")

# =========================
# RUN
# =========================

async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
