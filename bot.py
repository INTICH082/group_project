import os
import time
import asyncio
from enum import Enum
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv
import redis.asyncio as redis

# =========================
# ENV
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
redis_db = redis.from_url(REDIS_URL, decode_responses=True)

START_TIME = time.time()
LOGIN_TTL = 300  # 5 минут

# =========================
# ENUMS
# =========================

class UserStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    WAITING = "WAITING"
    AUTHORIZED = "AUTHORIZED"

# =========================
# REDIS HELPERS
# =========================

def user_key(chat_id: int):
    return f"user:{chat_id}"

async def get_user(chat_id: int):
    return await redis_db.hgetall(user_key(chat_id))

async def save_user(chat_id: int, data: dict):
    await redis_db.hset(user_key(chat_id), mapping=data)

async def delete_user(chat_id: int):
    await redis_db.delete(user_key(chat_id))

async def inc_commands():
    await redis_db.incr("stats:commands")

async def get_command_count():
    val = await redis_db.get("stats:commands")
    return int(val or 0)

async def get_active_users():
    keys = await redis_db.keys("user:*")
    count = 0
    for k in keys:
        u = await redis_db.hgetall(k)
        if u.get("status") == UserStatus.AUTHORIZED:
            count += 1
    return count

# =========================
# AUTH GUARD
# =========================

async def require_auth(message: types.Message):
    user = await get_user(message.chat.id)
    if not user or user.get("status") != UserStatus.AUTHORIZED:
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
    await inc_commands()
    name = message.from_user.first_name or "Пользователь"
    await message.answer(
        f"👋 <b>Привет, {name}!</b>\n\n"
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
        "/complete_login <code> — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test <id> — начать тест\n\n"
        "🌐 <b>Ссылки:</b>\n"
        "Web: http://localhost:3000\n"
        "Core API: http://core-service:8082\n"
        "Auth API: http://auth-service:8081"
    )

@dp.message_handler(commands=["help"])
async def help_cmd(message: types.Message):
    await inc_commands()
    name = message.from_user.first_name or "Пользователь"
    await message.answer(
        f"🤖 <b>ПОМОЩЬ И СПРАВКА</b>\n\n"
        f"👤 Пользователь: <b>{name}</b>\n\n"
        "🚀 <b>Команды:</b>\n"
        "/start — запуск бота\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/login — начать авторизацию\n"
        "/complete_login <code> — подтвердить вход\n"
        "/tests — список тестов\n"
        "/start_test <id> — запуск теста\n\n"
        "ℹ️ Используйте /status для проверки системы"
    )

@dp.message_handler(commands=["status"])
async def status_cmd(message: types.Message):
    await inc_commands()
    uptime = int((time.time() - START_TIME) // 60)
    commands = await get_command_count()
    active = await get_active_users()

    now = datetime.now(timezone.utc).strftime("%H:%M:%S")

    await message.answer(
        "📊 <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"Время (UTC): {now}\n"
        f"Активна: {uptime} мин\n\n"
        "<b>Сервисы:</b>\n"
        "• core-service: 🟢 Онлайн :8082\n"
        "• auth-service: 🟢 Онлайн :8081\n"
        "• web-client: 🟢 Онлайн :3000\n"
        "• postgres: 🟢 Онлайн :5432\n"
        "• mongodb: 🟢 Онлайн :27017\n"
        "• redis: 🟢 Онлайн :6379\n\n"
        "<b>Статистика:</b>\n"
        f"Команд выполнено: {commands}\n"
        f"Активных пользователей: {active}"
    )

@dp.message_handler(commands=["services"])
async def services_cmd(message: types.Message):
    await inc_commands()
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
    await inc_commands()
    code = str(int(time.time()))[-6:]

    await save_user(message.chat.id, {
        "status": UserStatus.WAITING,
        "code": code,
        "created": str(int(time.time()))
    })

    await message.answer(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        "Введите код в веб-клиенте:\n"
        f"<code>{code}</code>\n\n"
        "После подтверждения выполните:\n"
        "<code>/complete_login &lt;code&gt;</code>"
    )

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(message: types.Message):
    await inc_commands()
    args = message.get_args()
    user = await get_user(message.chat.id)

    if not user:
        await message.answer("❌ Сессия не найдена. Используйте /login")
        return

    if user.get("status") == UserStatus.AUTHORIZED:
        await message.answer("✅ Вы уже авторизованы")
        return

    if not args or args != user.get("code"):
        await message.answer("❌ Ошибка авторизации. Неверный код.")
        return

    created = int(user.get("created"))
    if time.time() - created > LOGIN_TTL:
        await delete_user(message.chat.id)
        await message.answer("❌ Время авторизации истекло. Используйте /login")
        return

    await save_user(message.chat.id, {"status": UserStatus.AUTHORIZED})
    await message.answer("✅ <b>АВТОРИЗАЦИЯ УСПЕШНА</b>")

@dp.message_handler(commands=["tests"])
async def tests_cmd(message: types.Message):
    await inc_commands()
    if not await require_auth(message):
        return
    await message.answer("🧪 <b>СПИСОК ТЕСТОВ</b>\n\n1️⃣ API Test\n2️⃣ Load Test\n3️⃣ UI Test")

@dp.message_handler(commands=["start_test"])
async def start_test_cmd(message: types.Message):
    await inc_commands()
    if not await require_auth(message):
        return
    await message.answer("🚀 <b>ТЕСТ ЗАПУЩЕН</b>")

@dp.message_handler()
async def unknown_cmd(message: types.Message):
    await inc_commands()
    await message.answer("❓ <b>Нет такой команды</b>")

# =========================
# RUN
# =========================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
