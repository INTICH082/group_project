import os
import time
import asyncio
from enum import Enum
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ParseMode
from dotenv import load_dotenv
import redis.asyncio as redis

# ==================================================
# ENV
# ==================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ==================================================
# INIT
# ==================================================

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)
redis_db = redis.from_url(REDIS_URL, decode_responses=True)

START_TIME = int(time.time())

# ==================================================
# CONSTANTS
# ==================================================

LOGIN_TTL = 300  # 5 минут

TESTS = {
    1: "API Test",
    2: "Load Test",
    3: "UI Test",
}

class UserStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    AUTHORIZED = "AUTHORIZED"

# ==================================================
# REDIS HELPERS
# ==================================================

def user_key(chat_id: int) -> str:
    return f"user:{chat_id}"

async def get_user(chat_id: int) -> dict:
    return await redis_db.hgetall(user_key(chat_id))

async def save_user(chat_id: int, data: dict):
    await redis_db.hset(user_key(chat_id), mapping=data)

async def delete_user(chat_id: int):
    await redis_db.delete(user_key(chat_id))

async def count_authorized_users() -> int:
    keys = await redis_db.keys("user:*")
    count = 0
    for k in keys:
        u = await redis_db.hgetall(k)
        if u.get("status") == UserStatus.AUTHORIZED:
            count += 1
    return count

# ==================================================
# STATS
# ==================================================

async def inc_command_counter():
    await redis_db.incr("stats:commands")

async def get_command_counter() -> int:
    return int(await redis_db.get("stats:commands") or 0)

# ==================================================
# DECORATOR
# ==================================================

async def require_auth(message: types.Message) -> bool:
    user = await get_user(message.chat.id)
    if user.get("status") != UserStatus.AUTHORIZED:
        await message.answer(
            "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
            "Для выполнения команды необходимо авторизоваться.\n\n"
            "🔐 Используйте:\n/login"
        )
        return False
    return True

# ==================================================
# COMMANDS
# ==================================================

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await inc_command_counter()
    name = message.from_user.first_name or "пользователь"

    await message.answer(
        f"👋 <b>Привет, {name}!</b>\n\n"
        "🤖 Я — бот системы тестирования.\n"
        "Система находится в стадии активной разработки.\n\n"
        "📌 <b>Основные команды:</b>\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/help — помощь\n"
        "/login — авторизация\n"
        "/complete_login — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test &lt;id&gt; — начать тест\n\n"
        "🌐 <b>Ссылки:</b>\n"
        "Web: http://localhost:3000\n"
        "Core API: http://core-service:8082\n"
        "Auth API: http://auth-service:8081"
    )

@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    await inc_command_counter()
    await message.answer(
        "🆘 <b>ПОМОЩЬ И СПРАВКА</b>\n\n"
        "🚀 /start — начать работу\n"
        "📊 /status — статус системы\n"
        "🧩 /services — сервисы\n"
        "🔐 /login — авторизация\n"
        "✅ /complete_login &lt;code&gt;\n"
        "🧪 /tests — список тестов\n"
        "▶ /start_test &lt;id&gt;\n"
    )

@dp.message_handler(commands=["status"])
async def cmd_status(message: types.Message):
    await inc_command_counter()

    now_utc = datetime.now(timezone.utc)
    uptime_min = (int(time.time()) - START_TIME) // 60

    commands_count = await get_command_counter()
    active_users = await count_authorized_users()

    await message.answer(
        "📊 <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"Время (UTC): {now_utc.strftime('%H:%M:%S')}\n"
        f"Активна: {uptime_min} мин\n\n"
        "Сервисы:\n"
        "• core-service: 🟢 Онлайн :8082\n"
        "• auth-service: 🟢 Онлайн :8081\n"
        "• web-client: 🟢 Онлайн :3000\n"
        "• postgres: 🟢 Онлайн :5432\n"
        "• mongodb: 🟢 Онлайн :27017\n"
        "• redis: 🟢 Онлайн :6379\n\n"
        "📈 <b>Статистика:</b>\n"
        f"Команд выполнено: {commands_count}\n"
        f"Активных пользователей: {active_users}"
    )

@dp.message_handler(commands=["services"])
async def cmd_services(message: types.Message):
    await inc_command_counter()
    await message.answer(
        "🧩 <b>СЕРВИСЫ СИСТЕМЫ</b>\n\n"
        "CORE-SERVICE — 🟢 Онлайн (8082)\n"
        "AUTH-SERVICE — 🟢 Онлайн (8081)\n"
        "WEB-CLIENT — 🟢 Онлайн (3000)\n"
        "POSTGRES — 🟢 5432\n"
        "MONGODB — 🟢 27017\n"
        "REDIS — 🟢 6379"
    )

# ==================================================
# AUTH
# ==================================================

@dp.message_handler(commands=["login"])
async def cmd_login(message: types.Message):
    await inc_command_counter()

    code = str(int(time.time()))[-6:]

    await save_user(message.chat.id, {
        "status": UserStatus.WAITING_CONFIRMATION,
        "code": code,
        "created_at": str(int(time.time()))
    })

    await message.answer(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        "Введите код в веб-клиенте:\n"
        f"<code>{code}</code>\n\n"
        "После подтверждения выполните:\n"
        "/complete_login <code>"
    )

@dp.message_handler(commands=["complete_login"])
async def cmd_complete_login(message: types.Message):
    await inc_command_counter()

    args = message.get_args()
    user = await get_user(message.chat.id)

    if not user:
        await message.answer("❌ Сессия не найдена. Используйте /login")
        return

    if user.get("status") != UserStatus.WAITING_CONFIRMATION:
        await message.answer("❌ Авторизация не начата")
        return

    if not args or args != user.get("code"):
        await message.answer("❌ Неверный код авторизации")
        return

    await save_user(message.chat.id, {
        "status": UserStatus.AUTHORIZED,
        "authorized_at": str(int(time.time()))
    })

    await message.answer("✅ <b>АВТОРИЗАЦИЯ УСПЕШНА</b>")

@dp.message_handler(commands=["logout"])
async def cmd_logout(message: types.Message):
    await inc_command_counter()
    await delete_user(message.chat.id)
    await message.answer("🚪 <b>СЕАНС ЗАВЕРШЁН</b>")

# ==================================================
# TESTS
# ==================================================

@dp.message_handler(commands=["tests"])
async def cmd_tests(message: types.Message):
    await inc_command_counter()
    if not await require_auth(message):
        return

    text = "🧪 <b>СПИСОК ТЕСТОВ</b>\n\n"
    for k, v in TESTS.items():
        text += f"{k}. {v}\n"

    await message.answer(text)

@dp.message_handler(commands=["start_test"])
async def cmd_start_test(message: types.Message):
    await inc_command_counter()
    if not await require_auth(message):
        return

    args = message.get_args()
    if not args or not args.isdigit():
        await message.answer("❌ Укажите ID теста")
        return

    test_id = int(args)
    if test_id not in TESTS:
        await message.answer("❌ Тест не найден")
        return

    await message.answer(
        f"▶ <b>ТЕСТ ЗАПУЩЕН</b>\n\n"
        f"Тест: {TESTS[test_id]}"
    )

# ==================================================
# FALLBACK
# ==================================================

@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer("❓ <b>Нет такой команды</b>")

# ==================================================
# START
# ==================================================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
