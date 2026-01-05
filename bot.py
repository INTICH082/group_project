import os
import time
import asyncio
from enum import Enum
from datetime import datetime
from zoneinfo import ZoneInfo

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

START_TIME = datetime.now(ZoneInfo("Europe/Moscow"))

LOGIN_TTL = 300  # 5 минут

TESTS = {
    "1": "API Test",
    "2": "Load Test",
    "3": "UI Test",
}

# ================== MODELS ==================

class Status(str, Enum):
    UNKNOWN = "UNKNOWN"
    ANONYMOUS = "ANONYMOUS"
    AUTHORIZED = "AUTHORIZED"

# ================== HELPERS ==================

def user_key(chat_id: int) -> str:
    return f"user:{chat_id}"

def moscow_time() -> datetime:
    return datetime.now(ZoneInfo("Europe/Moscow"))

async def inc_commands():
    await r.incr("stats:commands")

async def active_users() -> int:
    keys = await r.keys("user:*")
    count = 0
    for k in keys:
        if await r.hget(k, "status") == Status.AUTHORIZED:
            count += 1
    return count

# ================== COMMANDS ==================

@dp.message_handler(commands=["start"])
async def start_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        f"👋 <b>Привет, {m.from_user.first_name}!</b>\n"
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
        "/logout — выйти\n"
        "/tests — список тестов\n"
        "/start_test <id> — начать тест\n\n"
        "🌐 <b>Ссылки:</b>\n"
        "Web: http://localhost:3000\n"
        "Core API: http://core-service:8082\n"
        "Auth API: http://auth-service:8081"
    )

@dp.message_handler(commands=["help"])
async def help_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        "🆘 <b>ПОМОЩЬ И СПРАВКА</b>\n\n"
        "🚀 <b>Основные команды:</b>\n"
        "/start — начать работу\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/help — помощь\n"
        "/login — начать авторизацию\n"
        "/complete_login — завершить авторизацию\n"
        "/logout — выйти из системы\n"
        "/tests — список тестов\n"
        "/start_test <id> — запустить тест\n\n"
        "ℹ️ Используйте /status для проверки системы"
    )

@dp.message_handler(commands=["status"])
async def status_cmd(m: types.Message):
    await inc_commands()
    uptime = int((moscow_time() - START_TIME).total_seconds() // 60)

    await m.answer(
        "📊 <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"Время (МСК): {moscow_time().strftime('%H:%M:%S')}\n"
        f"Активна: {uptime} мин\n\n"
        "🟢 <b>Сервисы:</b>\n"
        "• core-service — 🟢 Онлайн :8082\n"
        "• auth-service — 🟢 Онлайн :8081\n"
        "• web-client — 🟢 Онлайн :3000\n"
        "• postgres — 🟢 Онлайн :5432\n"
        "• mongodb — 🟢 Онлайн :27017\n"
        "• redis — 🟢 Онлайн :6379\n\n"
        "📈 <b>Статистика:</b>\n"
        f"Команд выполнено: {await r.get('stats:commands') or 0}\n"
        f"Активных пользователей: {await active_users()}"
    )

@dp.message_handler(commands=["services"])
async def services_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        "🛠 <b>СЕРВИСЫ СИСТЕМЫ</b>\n\n"
        "CORE-SERVICE\nСтатус: 🟢 Онлайн\nПорт: 8082\n\n"
        "AUTH-SERVICE\nСтатус: 🟢 Онлайн\nПорт: 8081\n\n"
        "WEB-CLIENT\nСтатус: 🟢 Онлайн\nПорт: 3000\n\n"
        "POSTGRES — 5432\n"
        "MONGODB — 27017\n"
        "REDIS — 6379"
    )

@dp.message_handler(commands=["login"])
async def login_cmd(m: types.Message):
    await inc_commands()
    token = str(int(time.time()))[-6:]

    await r.hset(user_key(m.chat.id), mapping={
        "status": Status.ANONYMOUS,
        "login_token": token,
        "created_at": int(time.time())
    })

    await m.answer(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        "Введите код в веб-клиенте.\n"
        "Ожидайте подтверждения.\n\n"
        "После подтверждения выполните:\n"
        "/complete_login"
    )

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(m: types.Message):
    await inc_commands()
    data = await r.hgetall(user_key(m.chat.id))

    if not data:
        return await m.answer("❌ Сессия не найдена. Используйте /login")

    if data.get("status") == Status.AUTHORIZED:
        return await m.answer("✅ <b>АВТОРИЗАЦИЯ УСПЕШНА</b>")

    if data.get("status") == Status.ANONYMOUS:
        return await m.answer(
            "⏳ <b>ОЖИДАНИЕ ПОДТВЕРЖДЕНИЯ</b>\n"
            "Завершите вход в веб-клиенте."
        )

    await m.answer("❌ Авторизация не завершена")

@dp.message_handler(commands=["logout"])
async def logout_cmd(m: types.Message):
    await inc_commands()
    await r.delete(user_key(m.chat.id))
    await m.answer("🚪 <b>СЕАНС ЗАВЕРШЁН</b>")

@dp.message_handler(commands=["tests"])
async def tests_cmd(m: types.Message):
    await inc_commands()
    data = await r.hgetall(user_key(m.chat.id))

    if data.get("status") != Status.AUTHORIZED:
        return await m.answer("❌ Требуется авторизация")

    msg = "🧪 <b>СПИСОК ТЕСТОВ</b>\n\n"
    for k, v in TESTS.items():
        msg += f"{k}. {v}\n"
    await m.answer(msg)

@dp.message_handler(commands=["start_test"])
async def start_test_cmd(m: types.Message):
    await inc_commands()
    data = await r.hgetall(user_key(m.chat.id))

    if data.get("status") != Status.AUTHORIZED:
        return await m.answer("❌ Требуется авторизация")

    tid = m.get_args()
    if not tid or tid not in TESTS:
        return await m.answer("❌ Укажите корректный ID теста")

    await m.answer(f"🚀 Запуск теста: <b>{TESTS[tid]}</b>")

@dp.message_handler()
async def unknown_cmd(m: types.Message):
    await inc_commands()
    await m.answer("❓ Нет такой команды")

# ================== MOCK AUTH WATCHER ==================

async def auth_watcher():
    while True:
        keys = await r.keys("user:*")
        now = int(time.time())

        for k in keys:
            user = await r.hgetall(k)
            if user.get("status") == Status.ANONYMOUS:
                if now - int(user.get("created_at", now)) > LOGIN_TTL:
                    await r.delete(k)
        await asyncio.sleep(5)

async def on_startup(dp):
    asyncio.create_task(auth_watcher())

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
