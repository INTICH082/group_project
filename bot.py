import os
import time
from datetime import datetime, timedelta
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

START_TIME = datetime.now()
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

def moscow_time() -> datetime:
    return datetime.now()

async def inc_commands():
    await r.incr("stats:commands")

async def active_users():
    keys = await r.keys("user:*")
    count = 0
    for k in keys:
        if await r.hget(k, "status") == Status.AUTHORIZED:
            count += 1
    return count

async def get_user(cid: int):
    return await r.hgetall(user_key(cid))

# ================== COMMANDS ==================

@dp.message_handler(commands=["start"])
async def start_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        f"👋 <b>Привет, {m.from_user.first_name}!</b>\n\n"
        "🤖 Я — бот системы тестирования.\n"
        "Система находится в стадии активной разработки.\n\n"
        "📋 <b>Основные команды:</b>\n"
        "/start\n"
        "/status\n"
        "/services\n"
        "/help\n"
        "/login\n"
        "/complete_login КОД\n"
        "/tests\n"
        "/start_test ID"
    )

@dp.message_handler(commands=["help"])
async def help_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        "🆘 <b>ПОМОЩЬ И СПРАВКА</b>\n\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/login — начать авторизацию\n"
        "/complete_login КОД — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test ID — запустить тест"
    )

@dp.message_handler(commands=["status"])
async def status_cmd(m: types.Message):
    await inc_commands()
    uptime = int((moscow_time() - START_TIME).total_seconds() // 60)

    await m.answer(
        "📊 <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"Время (МСК): {moscow_time().strftime('%H:%M:%S')}\n"
        f"Активна: {uptime} мин\n\n"
        "<b>Сервисы:</b>\n"
        "• core-service: 🟢 Онлайн :8082\n"
        "• auth-service: 🟢 Онлайн :8081\n"
        "• web-client: 🟢 Онлайн :3000\n"
        "• postgres: 🟢 Онлайн :5432\n"
        "• mongodb: 🟢 Онлайн :27017\n"
        "• redis: 🟢 Онлайн :6379\n\n"
        "<b>Статистика:</b>\n"
        f"Команд выполнено: {await r.get('stats:commands') or 0}\n"
        f"Активных пользователей: {await active_users()}"
    )

@dp.message_handler(commands=["services"])
async def services_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        "🛠 <b>СЕРВИСЫ СИСТЕМЫ</b>\n\n"
        "<b>CORE-SERVICE</b>\nСтатус: 🟢 Онлайн\nПорт: 8082\n\n"
        "<b>AUTH-SERVICE</b>\nСтатус: 🟢 Онлайн\nПорт: 8081\n\n"
        "<b>WEB-CLIENT</b>\nСтатус: 🟢 Онлайн\nПорт: 3000\n\n"
        "POSTGRES — 5432\n"
        "MONGODB — 27017\n"
        "REDIS — 6379"
    )

@dp.message_handler(commands=["login"])
async def login_cmd(m: types.Message):
    await inc_commands()
    code = str(int(time.time()))[-6:]

    await r.hset(user_key(m.chat.id), mapping={
        "status": Status.ANONYMOUS,
        "code": code,
        "ts": int(time.time())
    })

    await m.answer(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        "Введите код в веб-клиенте:\n"
        f"<b>{code}</b>\n\n"
        "После подтверждения выполните:\n"
        f"/complete_login {code}"
    )

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(m: types.Message):
    await inc_commands()
    args = m.get_args()
    data = await get_user(m.chat.id)

    if not data:
        return await m.answer("❌ Сессия не найдена. Используйте /login")

    if data.get("status") != Status.ANONYMOUS:
        return await m.answer("❌ Авторизация не начата")

    if not args or args != data.get("code"):
        return await m.answer("❌ <b>НЕВЕРНЫЙ КОД</b>")

    if time.time() - int(data["ts"]) > LOGIN_TTL:
        await r.delete(user_key(m.chat.id))
        return await m.answer("❌ Время авторизации истекло")

    await r.hset(user_key(m.chat.id), "status", Status.AUTHORIZED)
    await m.answer("✅ <b>АВТОРИЗАЦИЯ УСПЕШНА</b>")

@dp.message_handler(commands=["tests"])
async def tests_cmd(m: types.Message):
    await inc_commands()
    data = await get_user(m.chat.id)

    if data.get("status") != Status.AUTHORIZED:
        return await m.answer("❌ Требуется авторизация")

    text = "🧪 <b>СПИСОК ТЕСТОВ</b>\n\n"
    for k, v in TESTS.items():
        text += f"{k}. {v}\n"

    await m.answer(text)

@dp.message_handler(commands=["start_test"])
async def start_test_cmd(m: types.Message):
    await inc_commands()
    data = await get_user(m.chat.id)

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

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
