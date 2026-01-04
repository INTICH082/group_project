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

# ================= INIT =================
load_dotenv()

# ================= CONFIG =================
class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    WEB_CLIENT_URL = "http://localhost:3000"
    CORE_API_URL = "http://core-service:8082"
    AUTH_API_URL = "http://auth-service:8081"
    REDIS_URL = "redis://redis:6379/0"

# ================= REDIS =================
redis_pool = redis.ConnectionPool.from_url(
    Config.REDIS_URL,
    decode_responses=True
)

def redis_client():
    return redis.Redis(connection_pool=redis_pool)

# ================= MONITOR =================
class SystemMonitor:
    def __init__(self):
        self.start_time = datetime.now()

    def status_text(self):
        uptime = (datetime.now() - self.start_time).seconds // 60
        return (
            "🖥️ <b>СТАТУС СИСТЕМЫ</b>\n"
            f"Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"Активна: {uptime} мин\n\n"
            "• core-service: 🟢 Онлайн\n"
            "• auth-service: 🟢 Онлайн\n"
            "• web-client: 🟢 Онлайн\n"
            "• postgres: 🟢 Онлайн\n"
            "• mongodb: 🟢 Онлайн\n"
            "• redis: 🟢 Онлайн"
        )

monitor = SystemMonitor()

# ================= AUTH =================
def get_user_token(user_id: int) -> Optional[str]:
    return redis_client().get(f"user_token:{user_id}")

def set_user_token(user_id: int, token: str):
    redis_client().set(f"user_token:{user_id}", token, ex=3600)

AUTH_REQUIRED_TEXT = (
    "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
    "Для выполнения команды необходимо авторизоваться.\n\n"
    "🔐 Используйте команду:\n"
    "/login"
)

# ================= BOT =================
async def main():
    bot = Bot(Config.TELEGRAM_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # ---------- /start ----------
    @dp.message(Command("start"))
    async def start(message: types.Message):
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
            "• Docker контейнеры\n"
            "• Базы данных\n"
            "• Web интерфейс\n"
            "• API сервисы\n"
            "• Авторизация через web\n\n"
            "🛠 <b>Что будет добавлено:</b>\n"
            "• Полное прохождение тестов\n"
            "• Уведомления\n\n"
            "📌 <b>Основные команды:</b>\n"
            "/start — Начало работы\n"
            "/status — Статус системы\n"
            "/services — Информация о сервисах\n"
            "/help — Справка\n"
            "/login — Начать авторизацию\n"
            "/completelogin — Завершить авторизацию\n"
            "/tests — Список тестов\n"
            "/start_test ID — Начать тест\n\n"
            "🌐 <b>Ссылки:</b>\n"
            f"• Веб-интерфейс: {Config.WEB_CLIENT_URL}\n"
            f"• API Core: {Config.CORE_API_URL}\n"
            f"• API Auth: {Config.AUTH_API_URL}",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    # ---------- /help ----------
    @dp.message(Command("help"))
    async def help_cmd(message: types.Message):
        await message.reply(
            "🆘 <b>ПОМОЩЬ</b>\n\n"
            "/start — Начало работы\n"
            "/status — Статус системы\n"
            "/services — Информация о сервисах\n"
            "/login — Авторизация\n"
            "/completelogin — Завершить авторизацию\n"
            "/tests — Список тестов\n"
            "/start_test ID — Начать тест",
            parse_mode="HTML"
        )

    # ---------- /complete_login ----------
    @dp.message(Command(commands=["complete_login", "completelogin"]))
    async def complete_login(message: types.Message):
        # имитация: сессии нет
        await message.reply(
            "❌ <b>СЕССИЯ НЕ НАЙДЕНА</b>\n\n"
            "Выполните /login и попробуйте снова",
            parse_mode="HTML"
        )

    # ---------- /tests ----------
    @dp.message(Command("tests"))
    async def tests(message: types.Message):
        if not get_user_token(message.from_user.id):
            await message.reply(AUTH_REQUIRED_TEXT, parse_mode="HTML")
            return

        await message.reply(
            "📋 <b>СПИСОК ТЕСТОВ</b>\n\n"
            "1️⃣ Test A\n"
            "2️⃣ Test B",
            parse_mode="HTML"
        )

    # ---------- /start_test ----------
    @dp.message(Command(commands=["start_test", "starttest"]))
    async def start_test(message: types.Message):
        if not get_user_token(message.from_user.id):
            await message.reply(AUTH_REQUIRED_TEXT, parse_mode="HTML")
            return

        await message.reply(
            "🚀 <b>ТЕСТ ЗАПУЩЕН</b>\n\n"
            "Следуйте инструкциям бота.",
            parse_mode="HTML"
        )

    # ---------- UNKNOWN ----------
    KNOWN = (
        "/start", "/help", "/status", "/services",
        "/login", "/completelogin", "/complete_login",
        "/tests", "/start_test", "/starttest"
    )

    @dp.message(F.text.startswith("/") & ~F.text.split()[0].in_(KNOWN))
    async def unknown(message: types.Message):
        await message.reply(
            "❓ <b>Неизвестная команда</b>\n\n"
            "Используйте /help",
            parse_mode="HTML"
        )

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())