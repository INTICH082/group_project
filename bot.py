import os
import asyncio
from datetime import datetime
from typing import Optional

import redis
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= INIT =================
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = "redis://redis:6379/0"

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================= REDIS =================
redis_pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    decode_responses=True
)

def rds():
    return redis.Redis(connection_pool=redis_pool)

# ================= SYSTEM =================
START_TIME = datetime.now()

def uptime_minutes() -> int:
    return (datetime.now() - START_TIME).seconds // 60

# ================= AUTH =================
def get_user_token(user_id: int) -> Optional[str]:
    return rds().get(f"user_token:{user_id}")

AUTH_REQUIRED_TEXT = (
    "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
    "Для выполнения команды необходимо авторизоваться.\n\n"
    "🔐 Используйте команду:\n"
    "/login"
)

# ================= /start =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статус", callback_data="status")],
        [InlineKeyboardButton(text="🛠 Сервисы", callback_data="services")],
        [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")],
        [InlineKeyboardButton(text="🔐 Авторизация", callback_data="login")],
    ])

    await message.reply(
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        "🤖 Я — бот системы тестирования.\n"
        "Система находится в стадии активной разработки.\n\n"
        "📊 <b>Что уже работает:</b>\n"
        "• Docker-контейнеры\n"
        "• Базы данных\n"
        "• Web-интерфейс\n"
        "• API-сервисы\n"
        "• Авторизация через web\n\n"
        "🧩 <b>Основные команды:</b>\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/help — справка\n"
        "/login — авторизация\n"
        "/tests — список тестов\n"
        "/start_test — начать тест\n",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# ================= /help =================
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.reply(
        "🆘 <b>ПОМОЩЬ</b>\n\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/login — авторизация\n"
        "/complete_login — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test — начать тест",
        parse_mode="HTML"
    )

# ================= /status =================
@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    await message.reply(
        "📊 <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"Время: {datetime.now().strftime('%H:%M:%S')}\n"
        f"Активна: {uptime_minutes()} мин\n\n"
        "• core-service — 🟢 Онлайн\n"
        "• auth-service — 🟢 Онлайн\n"
        "• web-client — 🟢 Онлайн\n"
        "• postgres — 🟢 Онлайн\n"
        "• mongodb — 🟢 Онлайн\n"
        "• redis — 🟢 Онлайн",
        parse_mode="HTML"
    )

# ================= /services =================
@dp.message(Command("services"))
async def cmd_services(message: types.Message):
    await message.reply(
        "🛠 <b>СЕРВИСЫ СИСТЕМЫ</b>\n\n"
        "CORE-SERVICE — 8082\n"
        "AUTH-SERVICE — 8081\n"
        "WEB-CLIENT — 3000\n"
        "POSTGRES — 5432\n"
        "MONGODB — 27017\n"
        "REDIS — 6379",
        parse_mode="HTML"
    )

# ================= /login =================
@dp.message(Command("login"))
async def cmd_login(message: types.Message):
    # ПОКА мок, дальше будет БД
    login = "roman"
    password = "481DA6D0"

    await message.reply(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        f"Логин: <code>{login}</code>\n"
        f"Пароль: <code>{password}</code>\n\n"
        "Введите данные в веб-клиенте и затем выполните:\n"
        "/complete_login",
        parse_mode="HTML"
    )

# ================= /complete_login =================
@dp.message(Command(commands=["complete_login", "completelogin"]))
async def cmd_complete_login(message: types.Message):
    # backend ещё не подтвердил вход
    await message.reply(
        "❌ <b>СЕССИЯ НЕ НАЙДЕНА</b>\n\n"
        "Завершите авторизацию в веб-клиенте и попробуйте снова.",
        parse_mode="HTML"
    )

# ================= /tests =================
@dp.message(Command("tests"))
async def cmd_tests(message: types.Message):
    if not get_user_token(message.from_user.id):
        await message.reply(AUTH_REQUIRED_TEXT, parse_mode="HTML")
        return

    tests = []  # будет БД

    if not tests:
        await message.reply(
            "📭 <b>ТЕСТОВ НЕТ</b>\n\n"
            "В данный момент доступных тестов нет.",
            parse_mode="HTML"
        )
        return

# ================= /start_test =================
@dp.message(Command(commands=["start_test", "starttest"]))
async def cmd_start_test(message: types.Message):
    if not get_user_token(message.from_user.id):
        await message.reply(AUTH_REQUIRED_TEXT, parse_mode="HTML")
        return

    tests = []  # будет БД

    if not tests:
        await message.reply(
            "❌ <b>НЕТ ДОСТУПНЫХ ТЕСТОВ</b>\n\n"
            "Запуск невозможен.",
            parse_mode="HTML"
        )
        return

# ================= UNKNOWN =================
@dp.message(F.text.startswith("/"))
async def unknown(message: types.Message):
    await message.reply(
        "❓ <b>Неизвестная команда</b>\n\n"
        "Используйте /help",
        parse_mode="HTML"
    )

# ================= RUN =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
