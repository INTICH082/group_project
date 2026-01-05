import os
import time
import asyncio
from datetime import datetime
from enum import Enum

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv
import redis.asyncio as redis

# ================== ENV ==================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ================== INIT ==================

bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
r = redis.from_url(REDIS_URL, decode_responses=True)

START_TIME = time.time()
LOGIN_TTL = 300  # 5 минут

TESTS = {
    "1": "API Test",
    "2": "Load Test",
    "3": "UI Test"
}

# ================== MODELS ==================

class Status(str, Enum):
    UNKNOWN = "UNKNOWN"
    ANONYMOUS = "ANONYMOUS"
    AUTHORIZED = "AUTHORIZED"

# ================== HELPERS ==================

def user_key(cid: int) -> str:
    return f"user:{cid}"

def moscow_time() -> str:
    return datetime.now().strftime("%H:%M:%S")

async def inc_commands():
    await r.incr("stats:commands")

async def active_users():
    keys = await r.keys("user:*")
    count = 0
    for k in keys:
        if await r.hget(k, "status") == Status.AUTHORIZED:
            count += 1
    return count

async def get_users_by_status(status: Status):
    keys = await r.keys("user:*")
    result = []
    for k in keys:
        data = await r.hgetall(k)
        if data.get("status") == status:
            result.append((int(k.split(":")[1]), data))
    return result

# ================== COMMANDS ==================

@dp.message_handler(commands=["start"])
async def start_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        f"👋 Привет, {m.from_user.first_name}!\n\n"
        "🤖 Я — бот системы тестирования.\n"
        "Система находится в стадии активной разработки.\n\n"

        "📊 Что уже работает:\n"
        "• Docker контейнеры\n"
        "• Базы данных\n"
        "• Веб-интерфейс\n"
        "• API-сервисы\n"
        "• Базовая авторизация\n\n"

        "🧭 Основные команды:\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/help — помощь\n"
        "/login — авторизация\n"
        "/complete_login — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test — начать тест\n"
        "/logout — выход\n\n"

        "🌐 Ссылки:\n"
        "Web: http://localhost:3000\n"
        "Core API: http://core-service:8082\n"
        "Auth API: http://auth-service:8081"
    )

@dp.message_handler(commands=["help"])
async def help_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        "🆘 <b>ПОМОЩЬ</b>\n\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/login — авторизация\n"
        "/complete_login — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test — начать тест\n"
        "/logout — выход"
    )

@dp.message_handler(commands=["status"])
async def status_cmd(m: types.Message):
    await inc_commands()
    uptime_min = int((time.time() - START_TIME) // 60)

    await m.answer(
        "🖥️ <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"Время: {moscow_time()}\n"
        f"Активна: {uptime_min} мин\n\n"

        "Сервисы:\n"
        "• core-service: 🟢 Онлайн :8082\n"
        "• auth-service: 🟢 Онлайн :8081\n"
        "• web-client: 🟢 Онлайн :3000\n"
        "• postgres: 🟢 Онлайн :5432\n"
        "• mongodb: 🟢 Онлайн :27017\n"
        "• redis: 🟢 Онлайн :6379\n\n"

        "Статистика:\n"
        f"Команд выполнено: {await r.get('stats:commands') or 0}\n"
        f"Активных пользователей: {await active_users()}\n\n"

        "🌐 Веб-интерфейс: http://localhost:3000\n"
        "🔧 API Core: http://core-service:8082\n"
        "🔐 API Auth: http://auth-service:8081"
    )

@dp.message_handler(commands=["services"])
async def services_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        "🛠 <b>СЕРВИСЫ СИСТЕМЫ</b>\n\n"
        "CORE-SERVICE\n"
        "Статус: 🟢 Онлайн\n"
        "Порт: 8082\n\n"
        "AUTH-SERVICE\n"
        "Статус: 🟢 Онлайн\n"
        "Порт: 8081\n\n"
        "WEB-CLIENT\n"
        "Статус: 🟢 Онлайн\n"
        "Порт: 3000\n\n"
        "POSTGRES — 5432\n"
        "MONGODB — 27017\n"
        "REDIS — 6379"
    )

# --------- login / complete_login / tests / start_test
# ❗ НЕ ТРОГАЕМ, оставляем как есть в твоей версии ❗

@dp.message_handler(commands=["logout"])
async def logout_cmd(m: types.Message):
    await inc_commands()
    data = await r.hgetall(user_key(m.chat.id))
    status = data.get("status")

    if status == Status.AUTHORIZED:
        await r.hset(user_key(m.chat.id), "status", Status.UNKNOWN)
        await m.answer("🚪 Сеанс завершён")

    elif status == Status.ANONYMOUS:
        await m.answer("Вы анонимны. Выход невозможен.")

    else:
        await m.answer("Вы не авторизированы. Выход невозможен.")

@dp.message_handler()
async def unknown_cmd(m: types.Message):
    await inc_commands()
    await m.answer("❓ Нет такой команды")

# ================== BACKGROUND TASKS ==================

async def login_polling():
    while True:
        users = await get_users_by_status(Status.ANONYMOUS)
        now = time.time()

        for chat_id, data in users:
            ts = int(data.get("ts", 0))
            if now - ts > LOGIN_TTL:
                await r.delete(user_key(chat_id))
                await bot.send_message(
                    chat_id,
                    "❌ Время авторизации истекло.\nПожалуйста, начните вход заново."
                )

        await asyncio.sleep(10)

async def notification_polling():
    while True:
        # Заглушка под Core API /notification
        await asyncio.sleep(30)

async def on_startup(dp):
    asyncio.create_task(login_polling())
    asyncio.create_task(notification_polling())

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
