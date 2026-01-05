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

bot = Bot(BOT_TOKEN, parse_mode="HTML")
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

async def inc_commands():
    await r.incr("stats:commands")

async def active_users():
    keys = await r.keys("user:*")
    count = 0
    for k in keys:
        if await r.hget(k, "status") == UserStatus.AUTHORIZED:
            count += 1
    return count

# ================== START ==================

@dp.message_handler(commands=["start"])
async def start_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        f"👋 Привет, {m.from_user.first_name}!\n\n"
        "🤖 Я — бот системы тестирования.\n"
        "Система находится в стадии активной разработки.\n\n"
        "📊 <b>Что уже работает:</b>\n"
        "• Docker контейнеры\n"
        "• Базы данных\n"
        "• Веб-интерфейс\n"
        "• API-сервисы\n"
        "• Базовая авторизация\n\n"
        "🧭 <b>Основные команды:</b>\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/help — помощь\n"
        "/login — авторизация\n"
        "/complete_login — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test — начать тест\n"
        "/logout — выход\n\n"
        "🌐 <b>Ссылки:</b>\n"
        "Web: http://localhost:3000\n"
        "Core API: http://core-service:8082\n"
        "Auth API: http://auth-service:8081"
    )

# ================== STATUS ==================

@dp.message_handler(commands=["status"])
async def status_cmd(m: types.Message):
    await inc_commands()
    uptime = int((now_moscow() - (START_TIME + MOSCOW_OFFSET)).total_seconds() // 60)

    await m.answer(
        "🖥️ <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"Время: {now_moscow().strftime('%H:%M:%S')}\n"
        f"Активна: {uptime} мин\n\n"
        "Сервисы:\n"
        "• core-service: 🟢 Онлайн :8082\n"
        "• auth-service: 🟢 Онлайн :8081\n"
        "• web-client: 🟢 Онлайн :3000\n"
        "• postgres: 🟢 Онлайн :5432\n"
        "• mongodb: 🟢 Онлайн :27017\n"
        "• redis: 🟢 Онлайн :6379\n\n"
        "<b>Статистика:</b>\n"
        f"Команд выполнено: {await r.get('stats:commands') or 0}\n"
        f"Активных пользователей: {await active_users()}\n\n"
        "🌐 Веб-интерфейс: http://localhost:3000\n"
        "🔧 API Core: http://core-service:8082\n"
        "🔐 API Auth: http://auth-service:8081"
    )

# ================== SERVICES ==================

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

# ================== HELP ==================

@dp.message_handler(commands=["help"])
async def help_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        "ℹ️ Помощь\n\n"
        "Доступные команды:\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/login — авторизация\n"
        "/complete_login — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test — начать тест\n"
        "/logout — выход"
    )

# ================== LOGIN / TESTS (НЕ ТРОГАЕМ) ==================
# ⬇️ логика 그대로, как ты сказал — идеальна

@dp.message_handler(commands=["login"])
async def login_cmd(m: types.Message):
    args = m.get_args()
    user = await get_user(m.chat.id)

    if not user:
        if not args:
            return await m.answer(
                "🔐 Вы не авторизованы.\n"
                "Доступные способы входа:\n"
                "• GitHub\n• Яндекс ID\n• По коду\n\n"
                "Для входа по коду:\n/login code"
            )

    if args == "code":
        token = secrets.token_hex(3)
        await set_user(m.chat.id, {
            "status": UserStatus.ANONYMOUS,
            "login_token": token,
            "ts": int(time.time())
        })
        return await m.answer(
            "🔑 Введите этот код в веб-клиенте:\n"
            f"<code>{token}</code>\n\n"
            "Ожидаю подтверждения…"
        )

    if user.get("status") == UserStatus.ANONYMOUS:
        return await m.answer("⏳ Авторизация ещё не завершена")

    if user.get("status") == UserStatus.AUTHORIZED:
        return await m.answer("✅ Вы уже авторизованы")

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(m: types.Message):
    user = await get_user(m.chat.id)
    if not user or user.get("status") != UserStatus.ANONYMOUS:
        return await m.answer("❌ Авторизация не начата")
    await m.answer("⏳ Ожидаю подтверждения из веб-клиента")

@dp.message_handler(commands=["tests"])
async def tests_cmd(m: types.Message):
    user = await get_user(m.chat.id)
    if user.get("status") != UserStatus.AUTHORIZED:
        return await m.answer("❌ Требуется авторизация")

    msg = "🧪 <b>СПИСОК ТЕСТОВ</b>\n\n"
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

    await m.answer(f"🚀 Запуск теста: <b>{TESTS[tid]}</b>")

# ================== LOGOUT ==================

@dp.message_handler(commands=["logout"])
async def logout_cmd(m: types.Message):
    user = await get_user(m.chat.id)

    if not user:
        return await m.answer("❌ Вы не авторизированы. Выход невозможен.")

    if user.get("status") == UserStatus.ANONYMOUS:
        return await m.answer("👤 Вы анонимны. Выход невозможен.")

    if user.get("status") == UserStatus.AUTHORIZED:
        await set_user(m.chat.id, {"status": UserStatus.UNKNOWN})
        return await m.answer("🚪 Сеанс завершён.")

# ================== FALLBACK ==================

@dp.message_handler()
async def unknown_cmd(m: types.Message):
    await inc_commands()
    await m.answer("❓ Нет такой команды")

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
