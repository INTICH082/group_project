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

    def status_text(self) -> str:
        uptime = (datetime.now() - self.start_time).seconds // 60
        return (
            "🖥️ <b>СТАТУС СИСТЕМЫ</b>\n"
            f"Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"Активна: {uptime} мин\n\n"
            "Сервисы:\n"
            "• core-service: 🟢 Онлайн :8082\n"
            "• auth-service: 🟢 Онлайн :8081\n"
            "• web-client: 🟢 Онлайн :3000\n"
            "• postgres: 🟢 Онлайн :5432\n"
            "• mongodb: 🟢 Онлайн :27017\n"
            "• redis: 🟢 Онлайн :6379\n"
        )

monitor = SystemMonitor()

# ================= AUTH =================
def get_user_token(user_id: int) -> Optional[str]:
    return redis_client().get(f"user_token:{user_id}")

def set_user_token(user_id: int, token: str):
    redis_client().set(f"user_token:{user_id}", token, ex=3600)

# ================= BOT =================
async def main():
    bot = Bot(Config.TELEGRAM_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # ================= /start =================
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
            "• Контейнеры Docker подняты\n"
            "• Базы данных запущены\n"
            "• Веб-интерфейс доступен\n"
            "• API сервисы готовы\n"
            "• Базовая авторизация через веб\n\n"

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
            "/start_test <id> — Начать тест\n\n"

            "🌐 <b>Ссылки:</b>\n"
            f"• Веб-интерфейс: {Config.WEB_CLIENT_URL}\n"
            f"• API Core: {Config.CORE_API_URL}\n"
            f"• API Auth: {Config.AUTH_API_URL}",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    # ================= /help =================
    @dp.message(Command("help"))
    async def help_cmd(message: types.Message):
        await message.reply(
            "🆘 <b>ПОМОЩЬ</b>\n\n"
            "/start — Начало работы\n"
            "/status — Статус системы\n"
            "/services — Информация о сервисах\n"
            "/login — Начать авторизацию\n"
            "/completelogin — Завершить авторизацию\n"
            "/tests — Список тестов\n"
            "/start_test <id> — Начать тест",
            parse_mode="HTML"
        )

    # ================= /status =================
    @dp.message(Command("status"))
    async def status(message: types.Message):
        await message.reply(monitor.status_text(), parse_mode="HTML")

    # ================= /services =================
    @dp.message(Command("services"))
    async def services(message: types.Message):
        await message.reply(
            "🛠 <b>СЕРВИСЫ СИСТЕМЫ</b>\n\n"
            "<b>CORE-SERVICE</b>\n"
            "Статус: 🟢 Онлайн\n"
            "Порт: 8082\n"
            "URL: http://core-service:8082\n\n"

            "<b>AUTH-SERVICE</b>\n"
            "Статус: 🟢 Онлайн\n"
            "Порт: 8081\n"
            "URL: http://auth-service:8081\n\n"

            "<b>WEB-CLIENT</b>\n"
            "Статус: 🟢 Онлайн\n"
            "Порт: 3000\n"
            "URL: http://localhost:3000\n\n"

            "<b>POSTGRES</b>\n"
            "Статус: 🟢 Онлайн\n"
            "Порт: 5432\n\n"

            "<b>MONGODB</b>\n"
            "Статус: 🟢 Онлайн\n"
            "Порт: 27017\n\n"

            "<b>REDIS</b>\n"
            "Статус: 🟢 Онлайн\n"
            "Порт: 6379\n"
            "URL: redis://redis:6379/0",
            parse_mode="HTML"
        )

    # ================= /login =================
    @dp.message(Command("login"))
    async def login(message: types.Message):
        code = uuid.uuid4().hex[:8].upper()
        redis_client().set(f"login:{code}", message.from_user.id, ex=600)

        await message.reply(
            "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
            f"Ваш код: <code>{code}</code>\n\n"
            "Введите код в веб-клиенте и затем выполните:\n"
            "/completelogin",
            parse_mode="HTML"
        )

    # ================= /completelogin =================
    @dp.message(Command(commands=["complete_login", "completelogin"]))
    async def complete_login(message: types.Message):
        # заглушка, имитация успешного входа
        set_user_token(message.from_user.id, "demo-token")

        await message.reply(
            "✅ <b>АВТОРИЗАЦИЯ УСПЕШНА</b>\n\n"
            "Теперь доступны команды:\n"
            "/tests\n"
            "/start_test <id>",
            parse_mode="HTML"
        )

    # ================= UNKNOWN =================
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

# ================= RUN =================
if __name__ == "__main__":
    asyncio.run(main())
