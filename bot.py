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

BOT_START_TS = int(time.time())

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

def moscow_time_str() -> str:
    # В контейнере время УЖЕ должно быть MSK
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

async def get_user(cid: int) -> dict:
    return await r.hgetall(user_key(cid))

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
        "/login — начать авторизацию\n"
        "/complete_login — завершить авторизацию\n"
        "/logout — выход\n"
        "/tests — список тестов\n"
        "/start_test &lt;id&gt; — запуск теста"
    )

@dp.message_handler(commands=["status"])
async def status_cmd(m: types.Message):
    await inc_commands()

    uptime_min = (int(time.time()) - BOT_START_TS) // 60

    await m.answer(
        "📊 <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"Время (МСК): {moscow_time_str()}\n"
        f"Время работы: {uptime_min} мин\n\n"
        "<b>Сервисы:</b>\n"
        "• core-service — 🟢 Онлайн\n"
        "• auth-service — 🟢 Онлайн\n"
        "• web-client — 🟢 Онлайн\n"
        "• postgres — 🟢 Онлайн\n"
        "• mongodb — 🟢 Онлайн\n"
        "• redis — 🟢 Онлайн\n\n"
        "<b>Статистика:</b>\n"
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

    user = await get_user(m.chat.id)

    if user.get("status") == Status.AUTHORIZED:
        return await m.answer("✅ <b>Вы уже авторизованы</b>")

    login_token = str(int(time.time()))[-6:]

    await r.hset(user_key(m.chat.id), mapping={
        "status": Status.ANONYMOUS,
        "login_token": login_token,
        "created_at": int(time.time())
    })

    await m.answer(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        "Введите код в веб-клиенте:\n"
        f"<code>{login_token}</code>\n\n"
        "После подтверждения выполните:\n"
        "/complete_login"
    )

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(m: types.Message):
    await inc_commands()

    user = await get_user(m.chat.id)

    if not user:
        return await m.answer("❌ Вы не авторизованы. Используйте /login")

    if user.get("status") != Status.ANONYMOUS:
        return await m.answer("❌ Авторизация не начата")

    # ❗ Здесь В БУДУЩЕМ будет запрос в auth-service
    return await m.answer(
        "⏳ <b>Ожидание подтверждения</b>\n\n"
        "Завершите вход в веб-клиенте"
    )

@dp.message_handler(commands=["logout"])
async def logout_cmd(m: types.Message):
    await inc_commands()

    user = await get_user(m.chat.id)

    if not user:
        return await m.answer("ℹ️ Вы не авторизованы")

    if user.get("status") == Status.AUTHORIZED:
        await r.delete(user_key(m.chat.id))
        return await m.answer("🚪 <b>Сеанс завершён</b>")

    if user.get("status") == Status.ANONYMOUS:
        return await m.answer("ℹ️ Вы анонимны (не авторизованы)")

    await m.answer("ℹ️ Вы не авторизованы")

@dp.message_handler(commands=["tests"])
async def tests_cmd(m: types.Message):
    await inc_commands()

    user = await get_user(m.chat.id)
    if user.get("status") != Status.AUTHORIZED:
        return await m.answer("❌ Требуется авторизация")

    text = "🧪 <b>ДОСТУПНЫЕ ТЕСТЫ</b>\n\n"
    for k, v in TESTS.items():
        text += f"{k}. {v}\n"

    await m.answer(text)

@dp.message_handler(commands=["start_test"])
async def start_test_cmd(m: types.Message):
    await inc_commands()

    user = await get_user(m.chat.id)
    if user.get("status") != Status.AUTHORIZED:
        return await m.answer("❌ Требуется авторизация")

    tid = m.get_args()
    if not tid or tid not in TESTS:
        return await m.answer("❌ Укажите корректный ID теста")

    await m.answer(f"🚀 Запуск теста: <b>{TESTS[tid]}</b>")

@dp.message_handler()
async def unknown_cmd(m: types.Message):
    await inc_commands()
    await m.answer("❓ Нет такой команды")

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
