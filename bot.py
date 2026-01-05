import asyncio
import os
import time

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv
import redis.asyncio as redis

# =========================
# INIT
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")

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

# =========================
# AUTH CHECK
# =========================

async def require_auth(message: Message) -> bool:
    user = await get_user(message.chat.id)
    if not user or user.get("status") != "AUTHORIZED":
        await message.answer(
            "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
            "Для выполнения команды необходимо авторизоваться.\n\n"
            "🔐 Используйте:\n/login"
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
        "🤖 Я — бот системы тестирования.\n\n"
        "📌 <b>Команды:</b>\n"
        "/start\n"
        "/help\n"
        "/status\n"
        "/services\n"
        "/login\n"
        "/complete_login\n"
        "/tests\n"
        "/start_test"
    )

@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "🆘 <b>ПОМОЩЬ</b>\n\n"
        "/start — главное меню\n"
        "/login — авторизация\n"
        "/tests — список тестов"
    )

@router.message(Command("status"))
async def status_cmd(message: Message):
    await message.answer("📊 <b>Система работает</b> 🟢")

@router.message(Command("services"))
async def services_cmd(message: Message):
    await message.answer(
        "🛠 <b>СЕРВИСЫ</b>\n\n"
        "CORE — 🟢 8082\n"
        "AUTH — 🟢 8081\n"
        "WEB — 🟢 3000\n\n"
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
        await message.answer("❌ <b>Сессия не найдена</b>\nИспользуйте /login")
        return

    # заглушка (потом будет Auth API)
    await set_user(message.chat.id, {"status": "AUTHORIZED"})

    await message.answer("✅ <b>Авторизация успешна</b>")

@router.message(Command("tests"))
async def tests_cmd(message: Message):
    if not await require_auth(message):
        return

    await message.answer("🧪 <b>Тестов нет</b>")

@router.message(Command("start_test"))
async def start_test_cmd(message: Message):
    if not await require_auth(message):
        return

    await message.answer("🚀 <b>Сначала выберите тест</b>")

@router.message(F.text)
async def unknown(message: Message):
    await message.answer("❓ <b>Неизвестная команда</b>\n/help")

# =========================
# RUN
# =========================

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
