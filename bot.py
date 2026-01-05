import os
import time
import asyncio
from enum import Enum

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv
import redis.asyncio as redis

# ==================================================
# ENV / INIT
# ==================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
redis_db = redis.from_url(REDIS_URL, decode_responses=True)

# ==================================================
# ARCHITECTURE CONSTANTS
# ==================================================

LOGIN_TTL = 120  # время жизни login_code (сек)

class UserStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    ANONYMOUS = "ANONYMOUS"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    AUTHORIZED = "AUTHORIZED"

# ==================================================
# REDIS LAYER (как Repository)
# ==================================================

def user_key(chat_id: int) -> str:
    return f"user:{chat_id}"

async def get_user(chat_id: int) -> dict:
    return await redis_db.hgetall(user_key(chat_id))

async def save_user(chat_id: int, data: dict):
    await redis_db.hset(user_key(chat_id), mapping=data)

async def delete_user(chat_id: int):
    await redis_db.delete(user_key(chat_id))

async def get_users_by_status(status: UserStatus):
    keys = await redis_db.keys("user:*")
    users = []

    for key in keys:
        user = await redis_db.hgetall(key)
        if user.get("status") == status:
            users.append((int(key.split(":")[1]), user))

    return users

# ==================================================
# AUTH CHECK (middleware-like)
# ==================================================

async def require_authorized(message: types.Message) -> bool:
    user = await get_user(message.chat.id)

    if not user or user.get("status") != UserStatus.AUTHORIZED:
        await message.answer(
            "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
            "Вы не авторизованы.\n"
            "Используйте /login"
        )
        return False

    return True

# ==================================================
# COMMANDS
# ==================================================

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "🤖 Я — Telegram клиент системы тестирования.\n\n"
        "Доступные команды:\n"
        "/status\n"
        "/login\n"
        "/complete_login\n"
        "/logout"
    )

@dp.message_handler(commands=["status"])
async def status_cmd(message: types.Message):
    await message.answer(
        "📊 <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"Время: <code>{time.strftime('%H:%M:%S')}</code>\n"
        "Активна: 🟢\n\n"
        "• core-service — 🟢 Онлайн\n"
        "• auth-service — 🟢 Онлайн\n"
        "• web-client — 🟢 Онлайн\n"
        "• postgres — 🟢 Онлайн\n"
        "• mongodb — 🟢 Онлайн\n"
        "• redis — 🟢 Онлайн"
    )

@dp.message_handler(commands=["login"])
async def login_cmd(message: types.Message):
    user = await get_user(message.chat.id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await message.answer("✅ <b>ВЫ УЖЕ АВТОРИЗОВАНЫ</b>")
        return

    login_code = str(int(time.time()))[-6:]

    await save_user(message.chat.id, {
        "status": UserStatus.WAITING_CONFIRMATION,
        "login_code": login_code,
        "created_at": str(int(time.time()))
    })

    await message.answer(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        f"Введите код в веб-клиенте:\n"
        f"<code>{login_code}</code>\n\n"
        "После этого выполните:\n"
        "/complete_login"
    )

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(message: types.Message):
    user = await get_user(message.chat.id)

    if not user:
        await message.answer("❌ Сессия не найдена. Используйте /login")
        return

    if user.get("status") == UserStatus.AUTHORIZED:
        await message.answer("✅ <b>АВТОРИЗАЦИЯ УСПЕШНА</b>")
        return

    if user.get("status") == UserStatus.WAITING_CONFIRMATION:
        await message.answer(
            "⏳ <b>ОЖИДАНИЕ ПОДТВЕРЖДЕНИЯ</b>\n\n"
            "Завершите вход в веб-клиенте."
        )
        return

    await message.answer("❌ Авторизация не завершена")

@dp.message_handler(commands=["logout"])
async def logout_cmd(message: types.Message):
    await delete_user(message.chat.id)
    await message.answer("🚪 <b>СЕАНС ЗАВЕРШЁН</b>")

@dp.message_handler()
async def unknown_cmd(message: types.Message):
    await message.answer("❓ <b>Нет такой команды</b>")

# ==================================================
# MOCK WEB + AUTH FLOW (ЗАМЕНЯЕТСЯ В БУДУЩЕМ)
# ==================================================

async def authorization_watcher():
    """
    Имитирует:
    Web Client + Auth Service
    В будущем:
    - HTTP запросы
    - JWT
    - проверки токенов
    """

    while True:
        users = await get_users_by_status(UserStatus.WAITING_CONFIRMATION)
        now = int(time.time())

        for chat_id, user in users:
            created_at = int(user.get("created_at", now))

            # Истёк код входа
            if now - created_at > LOGIN_TTL:
                await delete_user(chat_id)
                await bot.send_message(chat_id, "❌ Время входа истекло")
                continue

            # ===== MOCK успешного входа =====
            # ЗДЕСЬ БУДЕТ Auth-service
            if now - created_at > 10:
                await save_user(chat_id, {
                    "status": UserStatus.AUTHORIZED,
                    "access_token": "mock-access-token",
                    "refresh_token": "mock-refresh-token"
                })

                await bot.send_message(
                    chat_id,
                    "✅ <b>АВТОРИЗАЦИЯ УСПЕШНА</b>"
                )

        await asyncio.sleep(5)

# ==================================================
# STARTUP
# ==================================================

async def on_startup(dp):
    asyncio.create_task(authorization_watcher())

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
