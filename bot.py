import os
import asyncio
import uuid
from datetime import datetime
from typing import Optional

import redis
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================== INIT ==================
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = "redis://redis:6379/0"

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================== REDIS ==================
redis_pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    decode_responses=True
)

def rds():
    return redis.Redis(connection_pool=redis_pool)

# ================== SYSTEM ==================
START_TIME = datetime.now()

def uptime_minutes() -> int:
    return (datetime.now() - START_TIME).seconds // 60

# ================== AUTH ==================
def get_user_token(user_id: int) -> Optional[str]:
    return rds().get(f"user_token:{user_id}")

AUTH_REQUIRED_TEXT = (
    "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
    "Для выполнения команды необходимо авторизоваться.\n\n"
    "🔐 Используйте команду:\n"
    "/login"
)

# ================== /start ==================
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
        "/start — начало\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/help — справка\n"
        "/login — авторизация\n"
        "/completelogin — завершить вход\n"
        "/tests — список тестов\n"
        "/start_test ID — начать тест\n\n"
        "🌐 <b>Ссылки:</b>\n"
        "• Web: http://localhost:3000\n"
        "• Core API: http://core-service:8082\n"
        "• Auth API: http://auth-service:8081",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# ================== /help ==================
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.reply(
        "🆘 <b>ПОМОЩЬ</b>\n\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/login — авторизация\n"
        "/completelogin — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test ID — начать тест",
        parse_mode="HTML"
    )

# ================== /status ==================
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

# ================== /services ==================
@dp.message(Command("services"))
async def cmd_services(message: types.Message):
    await message.reply(
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
        "REDIS — 6379",
        parse_mode="HTML"
    )

# ================== /login ==================
@dp.message(Command("login"))
async def cmd_login(message: types.Message):
    user_id = message.from_user.id
    r = rds()

    if get_user_token(user_id):
        await message.reply(
            "✅ <b>ВЫ УЖЕ АВТОРИЗОВАНЫ</b>\n\n"
            "Дополнительных действий не требуется.",
            parse_mode="HTML"
        )
        return

    pending = r.get(f"login_pending:{user_id}")
    if pending:
        await message.reply(
            "⏳ <b>АВТОРИЗАЦИЯ УЖЕ НАЧАТА</b>\n\n"
            f"Ваш код: <code>{pending}</code>\n"
            "Введите его в веб-клиенте и затем выполните:\n"
            "/completelogin",
            parse_mode="HTML"
        )
        return

    code = uuid.uuid4().hex[:8].upper()
    r.set(f"login_code:{code}", user_id, ex=600)
    r.set(f"login_pending:{user_id}", code, ex=600)

    await message.reply(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        f"Ваш код: <code>{code}</code>\n\n"
        "Введите код в веб-клиенте и затем выполните:\n"
        "/completelogin",
        parse_mode="HTML"
    )

# ================== /complete_login ==================
@dp.message(Command(commands=["complete_login", "completelogin"]))
async def cmd_complete_login(message: types.Message):
    user_id = message.from_user.id
    r = rds()

    if get_user_token(user_id):
        await message.reply(
            "🎉 <b>АВТОРИЗАЦИЯ УСПЕШНА</b>\n\n"
            "Вы уже вошли в систему.",
            parse_mode="HTML"
        )
        return

    code = r.get(f"login_pending:{user_id}")
    if not code:
        await message.reply(
            "❌ <b>СЕССИЯ НЕ НАЙДЕНА</b>\n\n"
            "Выполните /login и попробуйте снова.",
            parse_mode="HTML"
        )
        return

    await message.reply(
        "⏳ <b>АВТОРИЗАЦИЯ НЕ ЗАВЕРШЕНА</b>\n\n"
        "Введите код в веб-клиенте и повторите команду.",
        parse_mode="HTML"
    )

# ================== /tests ==================
@dp.message(Command("tests"))
async def cmd_tests(message: types.Message):
    if not get_user_token(message.from_user.id):
        await message.reply(AUTH_REQUIRED_TEXT, parse_mode="HTML")
        return

    tests = []  # ← здесь будет API

    if not tests:
        await message.reply(
            "📭 <b>ТЕСТОВ НЕТ</b>\n\n"
            "В данный момент доступных тестов нет.",
            parse_mode="HTML"
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"🧪 {t['name']}",
                callback_data=f"start_test:{t['id']}"
            )]
            for t in tests
        ]
    )

    await message.reply(
        "📋 <b>ВЫБЕРИТЕ ТЕСТ</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# ================== /start_test ==================
@dp.message(Command(commands=["start_test", "starttest"]))
async def cmd_start_test(message: types.Message):
    if not get_user_token(message.from_user.id):
        await message.reply(AUTH_REQUIRED_TEXT, parse_mode="HTML")
        return

    await message.reply(
        "🚀 <b>ТЕСТ ЗАПУЩЕН</b>\n\n"
        "Следуйте инструкциям бота.",
        parse_mode="HTML"
    )

# ================== UNKNOWN ==================
KNOWN_COMMANDS = {
    "/start", "/help", "/status", "/services",
    "/login", "/completelogin", "/complete_login",
    "/tests", "/start_test", "/starttest"
}

@dp.message(F.text.startswith("/") & ~F.text.split()[0].in_(KNOWN_COMMANDS))
async def unknown(message: types.Message):
    await message.reply(
        "❓ <b>Неизвестная команда</b>\n\n"
        "Используйте /help",
        parse_mode="HTML"
    )

# ================== RUN ==================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
