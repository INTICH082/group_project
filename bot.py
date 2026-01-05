import asyncio
import logging
import os
import time
import secrets
from enum import Enum
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, executor, types
import aioredis

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("BOT_TOKEN", "CHANGE_ME")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# ================== REDIS ==================

r = aioredis.from_url(REDIS_URL, decode_responses=True)

def user_key(cid: int) -> str:
    return f"user:{cid}"

class UserStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    ANONYMOUS = "ANONYMOUS"
    AUTHORIZED = "AUTHORIZED"

# 🔑 КРИТИЧЕСКИ ВАЖНО
async def get_user(cid: int) -> dict:
    key = user_key(cid)
    data = await r.hgetall(key)

    if not data:
        data = {"status": UserStatus.UNKNOWN}
        await r.hset(key, mapping=data)

    return data

async def set_user(cid: int, data: dict):
    await r.hset(user_key(cid), mapping=data)

# ================== DATA ==================

TESTS = {
    "1": "Авторизация",
    "2": "Регистрация",
    "3": "Нагрузочный тест"
}

START_TS = time.time()

def moscow_time() -> str:
    tz = timezone(timedelta(hours=3))
    return datetime.now(tz).strftime("%H:%M:%S")

def uptime_minutes() -> int:
    return int((time.time() - START_TS) / 60)

# ================== START ==================

@dp.message_handler(commands=["start"])
async def start_cmd(m: types.Message):
    await get_user(m.chat.id)

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

# ================== STATUS ==================

@dp.message_handler(commands=["status"])
async def status_cmd(m: types.Message):
    await get_user(m.chat.id)

    await m.answer(
        "🖥️ <b>СТАТУС СИСТЕМЫ</b>\n"
        f"Время: {moscow_time()}\n"
        f"Активна: {uptime_minutes()} мин\n\n"
        "Сервисы:\n"
        "• core-service: 🟢 Онлайн :8082\n"
        "• auth-service: 🟢 Онлайн :8081\n"
        "• web-client: 🟢 Онлайн :3000\n"
        "• postgres: 🟢 Онлайн :5432\n"
        "• mongodb: 🟢 Онлайн :27017\n"
        "• redis: 🟢 Онлайн :6379\n\n"
        "Статистика:\n"
        "Команд выполнено: 3\n"
        "Активных пользователей: 1\n\n"
        "🌐 Веб-интерфейс: http://localhost:3000\n"
        "🔧 API Core: http://core-service:8082\n"
        "🔐 API Auth: http://auth-service:8081"
    )

# ================== SERVICES (STUB) ==================

@dp.message_handler(commands=["services"])
async def services_cmd(m: types.Message):
    await get_user(m.chat.id)
    await m.answer("📦 Список сервисов временно недоступен.")

# ================== HELP ==================

@dp.message_handler(commands=["help"])
async def help_cmd(m: types.Message):
    await m.answer(
        "ℹ️ <b>ПОМОЩЬ</b>\n\n"
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

@dp.message_handler(commands=["login"])
async def login_cmd(m: types.Message):
    args = m.get_args()
    user = await get_user(m.chat.id)

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
    if user.get("status") != UserStatus.ANONYMOUS:
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

    if user.get("status") == UserStatus.UNKNOWN:
        return await m.answer("❌ Вы не авторизированы. Выход невозможен.")

    if user.get("status") == UserStatus.ANONYMOUS:
        return await m.answer("👤 Вы анонимны. Выход невозможен.")

    if user.get("status") == UserStatus.AUTHORIZED:
        await set_user(m.chat.id, {"status": UserStatus.UNKNOWN})
        return await m.answer("🚪 Сеанс завершён.")

# ================== FALLBACK ==================

@dp.message_handler()
async def unknown_cmd(m: types.Message):
    await m.answer("❓ Нет такой команды. Используйте /help")

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
