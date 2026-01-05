import os
import time
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv
import redis.asyncio as redis

# =========================
# INIT
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
r = redis.from_url(REDIS_URL, decode_responses=True)

# =========================
# MOCK DB (ЗАМЕНИШЬ НА РЕАЛЬНУЮ)
# =========================

USERS_DB = {
    "admin": "admin123",
    "roman": "1234"
}

# =========================
# REDIS HELPERS
# =========================

def key(chat_id: int) -> str:
    return f"user:{chat_id}"

async def get_user(chat_id: int):
    return await r.hgetall(key(chat_id))

async def set_user(chat_id: int, data: dict):
    await r.hset(key(chat_id), mapping=data)

async def delete_user(chat_id: int):
    await r.delete(key(chat_id))

# =========================
# AUTH CHECK
# =========================

async def require_auth(message: types.Message) -> bool:
    user = await get_user(message.chat.id)
    if not user or user.get("status") != "AUTHORIZED":
        await message.answer(
            "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
            "Для выполнения команды необходимо авторизоваться.\n\n"
            "🔐 Используйте команду:\n/login"
        )
        return False
    return True

# =========================
# COMMANDS
# =========================

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    await message.answer(
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        "🤖 Я — бот системы тестирования.\n"
        "Система находится в стадии активной разработки.\n\n"
        "🧩 <b>Основные команды:</b>\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/login — авторизация\n"
        "/complete_login — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test — начать тест\n\n"
        "🌐 <b>Ссылки:</b>\n"
        "• Web: http://localhost:3000\n"
        "• Core API: http://core-service:8082\n"
        "• Auth API: http://auth-service:8081"
    )

@dp.message_handler(commands=["status"])
async def status_cmd(message: types.Message):
    await message.answer(
        "📊 <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"Время: {time.strftime('%H:%M:%S')}\n"
        "Активна: 6 мин\n\n"
        "• core-service — 🟢 Онлайн\n"
        "• auth-service — 🟢 Онлайн\n"
        "• web-client — 🟢 Онлайн\n"
        "• postgres — 🟢 Онлайн\n"
        "• mongodb — 🟢 Онлайн\n"
        "• redis — 🟢 Онлайн"
    )

@dp.message_handler(commands=["services"])
async def services_cmd(message: types.Message):
    await message.answer(
        "🛠 <b>СЕРВИСЫ СИСТЕМЫ</b>\n\n"
        "<b>CORE-SERVICE</b>\nСтатус: 🟢 Онлайн\nПорт: 8082\n\n"
        "<b>AUTH-SERVICE</b>\nСтатус: 🟢 Онлайн\nПорт: 8081\n\n"
        "<b>WEB-CLIENT</b>\nСтатус: 🟢 Онлайн\nПорт: 3000\n\n"
        "POSTGRES — 5432\nMONGODB — 27017\nREDIS — 6379"
    )

# =========================
# LOGIN FLOW
# =========================

@dp.message_handler(commands=["login"])
async def login_cmd(message: types.Message):
    user = await get_user(message.chat.id)

    if user and user.get("status") == "AUTHORIZED":
        await message.answer(
            "✅ <b>ВЫ УЖЕ АВТОРИЗОВАНЫ</b>\n\n"
            "Дополнительных действий не требуется."
        )
        return

    await set_user(message.chat.id, {"status": "WAIT_LOGIN"})
    await message.answer("🔐 <b>АВТОРИЗАЦИЯ</b>\n\nВведите логин:")

@dp.message_handler(lambda m: True)
async def login_steps(message: types.Message):
    user = await get_user(message.chat.id)
    if not user:
        return

    if user.get("status") == "WAIT_LOGIN":
        await set_user(message.chat.id, {
            "status": "WAIT_PASSWORD",
            "login": message.text
        })
        await message.answer("Введите пароль:")
        return

    if user.get("status") == "WAIT_PASSWORD":
        login = user.get("login")
        password = message.text

        if USERS_DB.get(login) != password:
            await delete_user(message.chat.id)
            await message.answer(
                "❌ <b>НЕВЕРНЫЕ ДАННЫЕ</b>\n\n"
                "Попробуйте снова:\n/login"
            )
            return

        await set_user(message.chat.id, {
            "status": "PENDING_WEB_CONFIRM"
        })

        await message.answer(
            "⏳ <b>ОЖИДАНИЕ ПОДТВЕРЖДЕНИЯ</b>\n\n"
            "Завершите вход в веб-клиенте."
        )
        return

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(message: types.Message):
    user = await get_user(message.chat.id)

    if not user or user.get("status") != "PENDING_WEB_CONFIRM":
        await message.answer(
            "❌ <b>АВТОРИЗАЦИЯ НЕ ЗАВЕРШЕНА</b>\n\n"
            "Сначала выполните /login"
        )
        return

    await set_user(message.chat.id, {"status": "AUTHORIZED"})
    await message.answer(
        "🎉 <b>АВТОРИЗАЦИЯ УСПЕШНА</b>\n\n"
        "Вы вошли в систему."
    )

# =========================
# TESTS
# =========================

@dp.message_handler(commands=["tests"])
async def tests_cmd(message: types.Message):
    if not await require_auth(message):
        return

    await message.answer(
        "🧪 <b>ТЕСТОВ НЕТ</b>\n\n"
        "В данный момент доступных тестов нет."
    )

@dp.message_handler(commands=["start_test"])
async def start_test_cmd(message: types.Message):
    if not await require_auth(message):
        return

    await message.answer(
        "🚫 <b>НЕТ ДОСТУПНЫХ ТЕСТОВ</b>\n\n"
        "Сначала выберите тест через /tests."
    )

# =========================
# FALLBACK
# =========================

@dp.message_handler()
async def unknown_cmd(message: types.Message):
    await message.answer(
        "❓ <b>Неизвестная команда</b>\n\n"
        "Используйте /help"
    )

# =========================
# RUN
# =========================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
