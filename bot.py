import os
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# =======================
# CONFIG
# =======================

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

MOSCOW_TZ_OFFSET = timedelta(hours=3)

# =======================
# TIME HELPERS
# =======================

START_TIME = datetime.utcnow()

def moscow_time() -> datetime:
    return datetime.utcnow() + MOSCOW_TZ_OFFSET

# =======================
# BOT INIT
# =======================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())

# =======================
# SIMPLE STATS (без Redis)
# =======================

COMMAND_COUNTER = 0
ACTIVE_USERS = set()

async def inc_commands(user_id: int):
    global COMMAND_COUNTER
    COMMAND_COUNTER += 1
    ACTIVE_USERS.add(user_id)

# =======================
# COMMANDS
# =======================

@dp.message_handler(commands=["start"])
async def start_cmd(m: types.Message):
    await inc_commands(m.from_user.id)

    text = (
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

        "🌐 Адреса сервисов:\n"
        "Web: http://localhost:3000\n"
        "Core API: http://localhost:8082\n"
        "Auth API: http://localhost:8081"
    )

    await m.answer(text)

# -----------------------

@dp.message_handler(commands=["status"])
async def status_cmd(m: types.Message):
    await inc_commands(m.from_user.id)

    uptime_minutes = int(
        (moscow_time() - (START_TIME + MOSCOW_TZ_OFFSET)).total_seconds() // 60
    )

    text = (
        "📊 СТАТУС СИСТЕМЫ\n\n"
        f"🕒 Время (МСК): {moscow_time().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⏱ Время работы: {uptime_minutes} мин\n\n"

        "Сервисы:\n"
        "• core-service — OK (8082)\n"
        "• auth-service — OK (8081)\n"
        "• web-client — OK (3000)\n"
        "• postgres — OK\n"
        "• mongodb — OK\n"
        "• redis — OK\n\n"

        f"Команд выполнено: {COMMAND_COUNTER}\n"
        f"Активных пользователей: {len(ACTIVE_USERS)}"
    )

    await m.answer(text)

# -----------------------

@dp.message_handler(commands=["help"])
async def help_cmd(m: types.Message):
    await inc_commands(m.from_user.id)

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

# -----------------------
# ЗАГЛУШКИ (НЕ МЕНЯЕМ ЛОГИКУ)
# -----------------------

@dp.message_handler(commands=["services"])
async def services_cmd(m: types.Message):
    await inc_commands(m.from_user.id)
    await m.answer("📦 Список сервисов временно недоступен.")

@dp.message_handler(commands=["login"])
async def login_cmd(m: types.Message):
    await inc_commands(m.from_user.id)
    await m.answer(
        "🔐 Авторизация\n\n"
        "Введите код в веб-клиенте для входа.\n"
        "После подтверждения используйте /complete_login"
    )

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(m: types.Message):
    await inc_commands(m.from_user.id)
    await m.answer("✅ Авторизация успешно завершена.")

@dp.message_handler(commands=["tests"])
async def tests_cmd(m: types.Message):
    await inc_commands(m.from_user.id)
    await m.answer("🧪 Доступные тесты:\n1. Demo Test")

@dp.message_handler(commands=["start_test"])
async def start_test_cmd(m: types.Message):
    await inc_commands(m.from_user.id)
    await m.answer("▶️ Для запуска теста укажите его номер.")

@dp.message_handler(commands=["logout"])
async def logout_cmd(m: types.Message):
    await inc_commands(m.from_user.id)
    await m.answer("🚪 Вы вышли из системы.")

# -----------------------
# FALLBACK
# -----------------------

@dp.message_handler()
async def unknown_cmd(m: types.Message):
    await inc_commands(m.from_user.id)
    await m.answer("❌ Нет такой команды. Используйте /help")

# =======================
# START
# =======================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
