import os
import asyncio
from datetime import datetime
from typing import Optional

import redis
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State

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

def uptime_minutes():
    return (datetime.now() - START_TIME).seconds // 60

# ================= AUTH =================
def is_authorized(user_id: int) -> bool:
    return bool(rds().get(f"user_token:{user_id}"))

AUTH_REQUIRED_TEXT = (
    "❌ <b>ДОСТУП ЗАПРЕЩЁН</b>\n\n"
    "Для выполнения команды необходимо авторизоваться.\n\n"
    "🔐 Используйте команду:\n"
    "/login"
)

# ================= FSM =================
class LoginFSM(StatesGroup):
    login = State()
    password = State()

# ================= /start =================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.reply(
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        "🤖 Я — бот системы тестирования.\n"
        "Система находится в стадии активной разработки.\n\n"
        "📊 <b>Что уже работает:</b>\n"
        "• Docker контейнеры\n"
        "• Базы данных\n"
        "• Web-интерфейс\n"
        "• API-сервисы\n"
        "• Базовая авторизация\n\n"
        "🧩 <b>Основные команды:</b>\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/help — помощь\n"
        "/login — авторизация\n"
        "/complete_login — завершить авторизацию\n"
        "/tests — список тестов\n"
        "/start_test — начать тест\n\n"
        "🌐 <b>Ссылки:</b>\n"
        "• Web: http://localhost:3000\n"
        "• Core API: http://core-service:8082\n"
        "• Auth API: http://auth-service:8081",
        parse_mode="HTML"
    )

# ================= /help =================
@dp.message(Command("help"))
async def help_cmd(message: types.Message):
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
async def status(message: types.Message):
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
async def services(message: types.Message):
    await message.reply(
        "🛠 <b>СЕРВИСЫ СИСТЕМЫ</b>\n\n"
        "<b>CORE-SERVICE</b>\n"
        "Статус: 🟢 Онлайн\n"
        "Порт: 8082\n\n"
        "<b>AUTH-SERVICE</b>\n"
        "Статус: 🟢 Онлайн\n"
        "Порт: 8081\n\n"
        "<b>WEB-CLIENT</b>\n"
        "Статус: 🟢 Онлайн\n"
        "Порт: 3000\n\n"
        "<b>POSTGRES</b> — 5432\n"
        "<b>MONGODB</b> — 27017\n"
        "<b>REDIS</b> — 6379",
        parse_mode="HTML"
    )

# ================= /login =================
@dp.message(Command("login"))
async def login(message: types.Message, state):
    await state.set_state(LoginFSM.login)
    await message.reply(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        "Введите логин:",
        parse_mode="HTML"
    )

@dp.message(LoginFSM.login)
async def login_step(message: types.Message, state):
    await state.update_data(login=message.text)
    await state.set_state(LoginFSM.password)
    await message.reply(
        "Введите пароль:",
        parse_mode="HTML"
    )

@dp.message(LoginFSM.password)
async def password_step(message: types.Message, state):
    data = await state.get_data()

    # ==== МОК ПРОВЕРКИ (ЗАМЕНИШЬ НА БД) ====
    if data["login"] == "roman" and message.text == "481DA6D0":
        rds().set(f"user_token:{message.from_user.id}", "ok", ex=3600)
        await message.reply(
            "🔑 <b>ДАННЫЕ ПРИНЯТЫ</b>\n\n"
            "Для завершения авторизации выполните:\n"
            "/complete_login",
            parse_mode="HTML"
        )
    else:
        await message.reply(
            "❌ <b>НЕВЕРНЫЕ ДАННЫЕ</b>\n\n"
            "Попробуйте снова: /login",
            parse_mode="HTML"
        )

    await state.clear()

# ================= /complete_login =================
@dp.message(Command(commands=["complete_login", "completelogin"]))
async def complete_login(message: types.Message):
    if is_authorized(message.from_user.id):
        await message.reply(
            "🎉 <b>АВТОРИЗАЦИЯ ЗАВЕРШЕНА</b>\n\n"
            "Вы успешно вошли в систему.",
            parse_mode="HTML"
        )
    else:
        await message.reply(
            "❌ <b>АВТОРИЗАЦИЯ НЕ ЗАВЕРШЕНА</b>\n\n"
            "Сначала выполните /login",
            parse_mode="HTML"
        )

# ================= /tests =================
@dp.message(Command("tests"))
async def tests(message: types.Message):
    if not is_authorized(message.from_user.id):
        await message.reply(AUTH_REQUIRED_TEXT, parse_mode="HTML")
        return

    tests = []

    if not tests:
        await message.reply(
            "📭 <b>ТЕСТОВ НЕТ</b>\n\n"
            "В данный момент доступных тестов нет.",
            parse_mode="HTML"
        )

# ================= /start_test =================
@dp.message(Command("start_test"))
async def start_test(message: types.Message):
    if not is_authorized(message.from_user.id):
        await message.reply(AUTH_REQUIRED_TEXT, parse_mode="HTML")
        return

    await message.reply(
        "❌ <b>НЕТ ДОСТУПНЫХ ТЕСТОВ</b>\n\n"
        "Запуск невозможен.",
        parse_mode="HTML"
    )

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
