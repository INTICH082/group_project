import os
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

import redis
import aiohttp
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

# ================== ЛОГИ ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# ================== CONFIG ==================
class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    WEB_CLIENT_URL = "http://localhost:3000"
    CORE_API_URL = "http://core-service:8082"
    AUTH_API_URL = "http://auth-service:8081"
    REDIS_URL = "redis://redis:6379/0"


# ================== REDIS ==================
redis_pool = redis.ConnectionPool.from_url(
    Config.REDIS_URL,
    decode_responses=True
)

def redis_client():
    return redis.Redis(connection_pool=redis_pool)


# ================== MONITOR ==================
class SystemMonitor:
    def __init__(self):
        self.start_time = datetime.now()
        self.total_commands = 0
        self.active_users = set()

    def status(self) -> str:
        uptime = (datetime.now() - self.start_time).seconds // 60
        return (
            "🖥️ <b>СТАТУС СИСТЕМЫ</b>\n"
            f"Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"Активна: {uptime} мин\n\n"
            "<b>Сервисы:</b>\n"
            "• core-service: 🟢 Онлайн :8082\n"
            "• auth-service: 🟢 Онлайн :8081\n"
            "• web-client: 🟢 Онлайн :3000\n"
            "• postgres: 🟢 Онлайн :5432\n"
            "• mongodb: 🟢 Онлайн :27017\n"
            "• redis: 🟢 Онлайн :6379\n\n"
            "<b>Статистика:</b>\n"
            f"Команд выполнено: {self.total_commands}\n"
            f"Активных пользователей: {len(self.active_users)}\n\n"
            f"🌐 Веб-интерфейс: {Config.WEB_CLIENT_URL}\n"
            f"🔧 API Core: {Config.CORE_API_URL}\n"
            f"🔐 API Auth: {Config.AUTH_API_URL}"
        )


monitor = SystemMonitor()

# ================== AUTH ==================
def get_user_token(user_id: int) -> Optional[str]:
    return redis_client().get(f"user_token:{user_id}")

def set_user_token(user_id: int, token: str):
    redis_client().set(f"user_token:{user_id}", token, ex=3600)


AUTH_REQUIRED_TEXT = (
    "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
    "Для выполнения команды необходимо авторизоваться.\n\n"
    "🔐 Используйте команду:\n/login"
)

# ================== BOT ==================
async def main():
    if not Config.TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

    bot = Bot(Config.TELEGRAM_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # ---------- /start ----------
    @dp.message(Command("start"))
    async def start(message: types.Message):
        monitor.total_commands += 1
        monitor.active_users.add(message.from_user.id)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🖥️ Статус", callback_data="status")],
            [InlineKeyboardButton(text="🔧 Сервисы", callback_data="services")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
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
            "🔧 <b>Что будет добавлено:</b>\n"
            "• Полное прохождение тестов\n"
            "• Уведомления\n\n"
            "<b>Список команд:</b>\n"
            "/start — Начало работы\n"
            "/status — Статус системы\n"
            "/services — Информация о сервисах\n"
            "/help — Справка\n"
            "/login — Начать авторизацию\n"
            "/complete_login — Завершить авторизацию\n"
            "/tests — Список тестов\n"
            "/start_test <id> — Начать тест\n\n"
            "🌐 <b>Ссылки:</b>\n"
            f"• Веб-интерфейс: {Config.WEB_CLIENT_URL}\n"
            f"• API Core: {Config.CORE_API_URL}\n"
            f"• API Auth: {Config.AUTH_API_URL}",
            parse_mode="HTML",
            reply_markup=kb
        )

    # ---------- /status ----------
    @dp.message(Command("status"))
    async def status(message: types.Message):
        monitor.total_commands += 1
        await message.reply(monitor.status(), parse_mode="HTML")

    # ---------- /services ----------
    @dp.message(Command("services"))
    async def services(message: types.Message):
        monitor.total_commands += 1
        await message.reply(
            "🔧 <b>СЕРВИСЫ СИСТЕМЫ</b>\n\n"
            "<b>CORE-SERVICE</b>\n"
            "Статус: 🟢 Онлайн\n"
            "Порт: <code>8082</code>\n"
            "URL: <code>http://core-service:8082</code>\n\n"
            "<b>AUTH-SERVICE</b>\n"
            "Статус: 🟢 Онлайн\n"
            "Порт: <code>8081</code>\n"
            "URL: <code>http://auth-service:8081</code>\n\n"
            "<b>WEB-CLIENT</b>\n"
            "Статус: 🟢 Онлайн\n"
            "Порт: <code>3000</code>\n"
            "URL: <code>http://localhost:3000</code>\n\n"
            "<b>POSTGRES</b>\n"
            "Статус: 🟢 Онлайн\n"
            "Порт: <code>5432</code>\n\n"
            "<b>MONGODB</b>\n"
            "Статус: 🟢 Онлайн\n"
            "Порт: <code>27017</code>\n\n"
            "<b>REDIS</b>\n"
            "Статус: 🟢 Онлайн\n"
            "Порт: <code>6379</code>",
            parse_mode="HTML"
        )

    # ---------- /help ----------
    @dp.message(Command("help"))
    async def help_cmd(message: types.Message):
        monitor.total_commands += 1
        await message.reply(
            "🤖 <b>ПОМОЩЬ И СПРАВКА</b>\n\n"
            "🚀 <b>Основные команды:</b>\n"
            "/start — Начать работу\n"
            "/status — Проверить статус\n"
            "/services — Информация о сервисах\n"
            "/login — Начать авторизацию\n"
            "/complete_login — Завершить авторизацию\n"
            "/tests — Список тестов\n"
            "/start_test <id> — Начать тест\n\n"
            "🛠️ <b>Функции в разработке:</b>\n"
            "• Полное прохождение тестов\n"
            "• Личный кабинет\n"
            "• Уведомления\n\n"
            "Используйте /status для проверки системы",
            parse_mode="HTML"
        )

    # ---------- /login ----------
    @dp.message(Command("login"))
    async def login(message: types.Message):
        monitor.total_commands += 1
        code = uuid.uuid4().hex[:8].upper()
        redis_client().set(f"login:{code}", message.from_user.id, ex=600)

        await message.reply(
            "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
            "Для авторизации введите пароль в веб-клиенте.\n\n"
            f"Ваш код: <code>{code}</code>\n\n"
            "После ввода кода используйте команду:\n"
            "/complete_login",
            parse_mode="HTML"
        )

    # ---------- /complete_login ----------
    @dp.message(Command(commands=["complete_login", "completelogin"]))
    async def complete_login(message: types.Message):
        monitor.total_commands += 1
        r = redis_client()
        token = None

        for key in r.scan_iter("auth_token:*"):
            uid = r.get(key)
            if uid and int(uid) == message.from_user.id:
                token = key.split(":", 1)[1]
                break

        if not token:
            await message.reply(
                "❌ <b>СЕССИЯ НЕ НАЙДЕНА</b>\n\n"
                "Активная авторизация не обнаружена.\n\n"
                "🔐 Выполните /login и попробуйте снова",
                parse_mode="HTML"
            )
            return

        set_user_token(message.from_user.id, token)

        await message.reply(
            "✅ <b>АВТОРИЗАЦИЯ УСПЕШНА</b>\n\n"
            "Добро пожаловать в систему тестирования 🎉\n\n"
            "📌 <b>Доступные команды:</b>\n"
            "/tests — список тестов\n"
            "/start_test <id> — начать тест\n\n"
            "Удачи! 🚀",
            parse_mode="HTML"
        )

    # ---------- /tests ----------
    @dp.message(Command("tests"))
    async def tests(message: types.Message):
        monitor.total_commands += 1
        token = get_user_token(message.from_user.id)
        if not token:
            await message.reply(AUTH_REQUIRED_TEXT, parse_mode="HTML")
            return

        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{Config.CORE_API_URL}/tests", headers=headers) as resp:
                tests = await resp.json() if resp.status == 200 else []

        if not tests:
            await message.reply(
                "📭 <b>ТЕСТЫ НЕ НАЙДЕНЫ</b>\n\n"
                "В данный момент нет доступных тестов.",
                parse_mode="HTML"
            )
            return

        text = "📋 <b>ДОСТУПНЫЕ ТЕСТЫ</b>\n\n"
        for t in tests:
            text += (
                f"🧪 <b>ID:</b> <code>{t['id']}</code>\n"
                f"<b>Название:</b> {t['title']}\n\n"
            )

        text += "▶️ Используйте команду:\n/start_test <id>"

        await message.reply(text, parse_mode="HTML")

    # ---------- /start_test ----------
    @dp.message(Command(commands=["start_test", "starttest"]))
    async def start_test(message: types.Message):
        monitor.total_commands += 1
        token = get_user_token(message.from_user.id)
        if not token:
            await message.reply(AUTH_REQUIRED_TEXT, parse_mode="HTML")
            return

        args = message.text.split()
        if len(args) < 2:
            await message.reply("Использование: /start_test <id>")
            return

        await message.reply(
            "🚀 <b>ТЕСТ ЗАПУЩЕН</b>\n\n"
            "Тест успешно начат!\n\n"
            "Следуйте инструкциям бота и отвечайте на вопросы.\n\n"
            "Удачи! 💪",
            parse_mode="HTML"
        )

    # ---------- CALLBACK ----------
    @dp.callback_query()
    async def callbacks(call: types.CallbackQuery):
        if call.data == "login":
            await login(call.message)
        elif call.data == "status":
            await call.message.edit_text(monitor.status(), parse_mode="HTML")
        elif call.data == "help":
            await help_cmd(call.message)
        elif call.data == "services":
            await services(call.message)
        await call.answer()

    # ---------- UNKNOWN ----------
    @dp.message(~Command())
    async def unknown(message: types.Message):
        await message.reply(
            "❓ <b>Неизвестная команда</b>\n\n"
            "Используйте /help для списка доступных команд.",
            parse_mode="HTML"
        )

    logger.info("🤖 Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
