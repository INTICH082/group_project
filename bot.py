import os
import time
from datetime import datetime
from enum import Enum

import pytz
import redis.asyncio as redis
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

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

MSK = pytz.timezone("Europe/Moscow")
START_TIME = datetime.now(MSK)

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

def now_msk() -> datetime:
    return datetime.now(MSK)

async def inc_commands():
    await r.incr("stats:commands")

async def active_users() -> int:
    keys = await r.keys("user:*")
    count = 0
    for k in keys:
        if await r.hget(k, "status") == Status.AUTHORIZED:
            count += 1
    return count

async def get_user(chat_id: int) -> dict:
    return await r.hgetall(user_key(chat_id))

# ================== COMMANDS ==================

@dp.message_handler(commands=["start"])
async def start_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        f"👋 <b>Привет, {m.from_user.first_name}!</b>\n\n"
        "🤖 Я — бот системы тестирования.\n"
        "Система находится в стадии активной разработки.\n\n"
        "📋 <b>Основные команды:</b>\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/help — помощь\n"
        "/login — авторизация\n"
        "/complete_login <code> — завершить вход\n"
        "/tests — список тестов\n"
        "/start_test <id> — начать тест\n\n"
        "🌐 Web: http://localhost:3000\n"
        "🔗 Core API: http://core-service:8082\n"
        "🔐 Auth API: http://auth-service:8081"
    )

@dp.message_handler(commands=["help"])
async def help_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        "🆘 <b>ПОМОЩЬ</b>\n\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — информация о сервисах\n"
        "/login — начать авторизацию\n"
        "/complete_login <code> — подтвердить вход\n"
        "/tests — список тестов (нужна авторизация)\n"
        "/start_test <id> — запустить тест\n"
    )

@dp.message_handler(commands=["status"])
async def status_cmd(m: types.Message):
    await inc_commands()
    uptime = int((now_msk() - START_TIME).total_seconds() // 60)

    await m.answer(
        "📊 <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"Время (МСК): {now_msk().strftime('%H:%M:%S')}\n"
        f"Активна: {uptime} мин\n\n"
        "Сервисы:\n"
        "• core-service 🟢 Онлайн :8082\n"
        "• auth-service 🟢 Онлайн :8081\n"
        "• web-client 🟢 Онлайн :3000\n"
        "• postgres 🟢 Онлайн :5432\n"
        "• mongodb 🟢 Онлайн :27017\n"
        "• redis 🟢 Онлайн :6379\n\n"
        "📈 <b>Статистика:</b>\n"
        f"Команд выполнено: {await r.get('stats:commands') or 0}\n"
        f"Активных пользователей: {await active_users()}"
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

@dp.message_handler(commands=["login"])
async def login_cmd(m: types.Message):
    await inc_commands()
    user = await get_user(m.chat.id)

    if user and user.get("status") == Status.AUTHORIZED:
        return await m.answer("✅ Вы уже авторизованы")

    code = str(int(time.time()))[-6:]

    await r.hset(
        user_key(m.chat.id),
        mapping={
            "status": Status.ANONYMOUS,
            "login_code": code,
            "ts": int(time.time()),
        }
    )

    # 🔜 здесь будет вызов auth-service
    await m.answer(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        f"Введите код в веб-клиенте:\n<code>{code}</code>\n\n"
        "После подтверждения выполните:\n"
        "/complete_login <code>"
    )

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(m: types.Message):
    await inc_commands()
    args = m.get_args()
    user = await get_user(m.chat.id)

    if not user:
        return await m.answer("❌ Сессия не найдена. Используйте /login")

    if user.get("status") != Status.ANONYMOUS:
        return await m.answer("❌ Авторизация не начата")

    if not args or args != user.get("login_code"):
        return await m.answer("❌ <b>ОШИБКА АВТОРИЗАЦИИ</b>\nНеверный код")

    if time.time() - int(user.get("ts", 0)) > LOGIN_TTL:
        await r.delete(user_key(m.chat.id))
        return await m.answer("❌ Время авторизации истекло")

    # 🔜 здесь будет ответ от auth-service (access + refresh)
    await r.hset(
        user_key(m.chat.id),
        mapping={
            "status": Status.AUTHORIZED,
            "access_token": "mock-access",
            "refresh_token": "mock-refresh",
        }
    )

    await m.answer("✅ <b>АВТОРИЗАЦИЯ УСПЕШНА</b>")

@dp.message_handler(commands=["logout"])
async def logout_cmd(m: types.Message):
    await inc_commands()
    await r.delete(user_key(m.chat.id))
    await m.answer("🚪 Сеанс завершён")

@dp.message_handler(commands=["tests"])
async def tests_cmd(m: types.Message):
    await inc_commands()
    user = await get_user(m.chat.id)

    if user.get("status") != Status.AUTHORIZED:
        return await m.answer("❌ Требуется авторизация")

    msg = "🧪 <b>СПИСОК ТЕСТОВ</b>\n\n"
    for k, v in TESTS.items():
        msg += f"{k}. {v}\n"

    await m.answer(msg)

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
