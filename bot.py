import os
import time
import secrets
from datetime import datetime, timedelta
from enum import Enum

from aiogram import Bot, Dispatcher, executor, types
import redis.asyncio as redis

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

MOSCOW_OFFSET = timedelta(hours=3)

# ================== INIT ==================

bot = Bot(BOT_TOKEN)
dp = Dispatcher(bot)
r = redis.from_url(REDIS_URL, decode_responses=True)

START_TIME = datetime.utcnow()

# ================== MODELS ==================

class UserStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    ANONYMOUS = "ANONYMOUS"
    AUTHORIZED = "AUTHORIZED"

TESTS = {
    "1": "API Test",
    "2": "Load Test",
    "3": "UI Test"
}

# ================== HELPERS ==================

def now_moscow():
    return datetime.utcnow() + MOSCOW_OFFSET

def user_key(cid: int) -> str:
    return f"user:{cid}"

async def get_user(cid: int):
    return await r.hgetall(user_key(cid))

async def set_user(cid: int, data: dict):
    await r.hset(user_key(cid), mapping=data)

async def delete_user(cid: int):
    await r.delete(user_key(cid))

# ================== COMMANDS ==================

@dp.message_handler(commands=["start"])
async def start_cmd(m: types.Message):
    await m.answer(
        f"👋 Привет, {m.from_user.first_name}!\n\n"
        "🤖 Я — бот системы тестирования.\n"
        "Система находится в стадии активной разработки.\n\n"
        "🧭 Основные команды:\n"
        "/start\n/status\n/services\n/help\n/login\n/complete_login\n/tests\n/start_test\n/logout\n"
    )

@dp.message_handler(commands=["status"])
async def status_cmd(m: types.Message):
    uptime = int((now_moscow() - (START_TIME + MOSCOW_OFFSET)).total_seconds() // 60)
    await m.answer(
        f"📊 Статус системы\n\n"
        f"Время (МСК): {now_moscow().strftime('%H:%M:%S')}\n"
        f"Время работы: {uptime} мин"
    )

@dp.message_handler(commands=["services"])
async def services_cmd(m: types.Message):
    await m.answer(
        "🛠 СЕРВИСЫ\n\n"
        "core-service : 8082\n"
        "auth-service : 8081\n"
        "web-client   : 3000\n"
        "redis        : 6379"
    )

@dp.message_handler(commands=["help"])
async def help_cmd(m: types.Message):
    await m.answer(
        "🆘 Помощь\n\n"
        "/login — авторизация\n"
        "/logout — выход\n"
        "/tests — список тестов\n"
        "/start_test <id>"
    )

# ================== LOGIN ==================

@dp.message_handler(commands=["login"])
async def login_cmd(m: types.Message):
    args = m.get_args()
    user = await get_user(m.chat.id)

    # UNKNOWN
    if not user:
        if not args:
            return await m.answer(
                "🔐 Вы не авторизованы.\n"
                "Доступные способы входа:\n"
                "• GitHub\n• Яндекс ID\n• По коду\n\n"
                "Для входа по коду:\n/login code"
            )

    # login code
    if args == "code":
        token = secrets.token_hex(3)
        await set_user(m.chat.id, {
            "status": UserStatus.ANONYMOUS,
            "login_token": token,
            "ts": int(time.time())
        })
        return await m.answer(
            "🔑 Введите этот код в веб-клиенте:\n"
            f"{token}\n\n"
            "Ожидаю подтверждения…"
        )

    # ANONYMOUS
    if user.get("status") == UserStatus.ANONYMOUS:
        return await m.answer("⏳ Авторизация ещё не завершена")

    # AUTHORIZED
    if user.get("status") == UserStatus.AUTHORIZED:
        return await m.answer("✅ Вы уже авторизованы")

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(m: types.Message):
    user = await get_user(m.chat.id)

    if not user or user.get("status") != UserStatus.ANONYMOUS:
        return await m.answer("❌ Авторизация не начата")

    # ⛔ здесь НЕТ генерации кода
    # ⛔ здесь НЕТ автологина
    # ⛔ здесь ТОЛЬКО проверка (заглушка)

    return await m.answer("⏳ Ожидаю подтверждения из веб-клиента")

# ================== LOGOUT ==================

@dp.message_handler(commands=["logout"])
async def logout_cmd(m: types.Message):
    user = await get_user(m.chat.id)

    if not user:
        return await m.answer("👤 Вы анонимны")

    if user.get("status") == UserStatus.AUTHORIZED:
        await set_user(m.chat.id, {"status": UserStatus.UNKNOWN})
        return await m.answer("🚪 Вы вышли из системы")

    return await m.answer("❌ Вы не авторизованы")

# ================== TESTS ==================

@dp.message_handler(commands=["tests"])
async def tests_cmd(m: types.Message):
    user = await get_user(m.chat.id)
    if user.get("status") != UserStatus.AUTHORIZED:
        return await m.answer("❌ Требуется авторизация")

    msg = "🧪 Доступные тесты:\n"
    for k, v in TESTS.items():
        msg += f"{k}. {v}\n"
    await m.answer(msg)

@dp.message_handler(commands=["start_test"])
async def start_test_cmd(m: types.Message):
    user = await get_user(m.chat.id)
    if user.get("status") != UserStatus.AUTHORIZED:
        return await m.answer("❌ Требуется авторизация")

    tid = m.get_args()
    if tid not in TESTS:
        return await m.answer("❌ Укажите корректный ID теста")

    await m.answer(f"🚀 Запуск теста: {TESTS[tid]}")

# ================== FALLBACK ==================

@dp.message_handler()
async def unknown_cmd(m: types.Message):
    await m.answer("❓ Нет такой команды")

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
