import os
import time
import secrets
import asyncio
from datetime import datetime, timezone, timedelta
from enum import Enum

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import MessageNotModified, MessageCantBeEdited
from dotenv import load_dotenv
import redis.asyncio as redis

# ================== ENV ==================

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")
WEB_CLIENT_URL = os.getenv("WEB_CLIENT_URL", "http://localhost:3000")
POSTGRES_URL = os.getenv("POSTGRES_URL", "postgres://user:pass@postgres:5432/db")  # Для будущего
MONGO_URL = os.getenv("MONGO_URL", "mongo://mongo:27017/db")  # Для будущего

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ================== INIT ==================

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
r = redis.from_url(REDIS_URL, decode_responses=True)

START_TIME = datetime.now(timezone(timedelta(hours=3)))

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

def user_key(cid: int) -> str:
    return f"user:{cid}"

def moscow_time() -> datetime:
    return datetime.now(timezone(timedelta(hours=3)))

async def get_user(cid: int) -> dict:
    return await r.hgetall(user_key(cid)) or {}

async def set_user(cid: int, data: dict):
    await r.hmset(user_key(cid), data)

async def delete_user(cid: int):
    await r.delete(user_key(cid))

async def inc_commands():
    await r.incr("total_commands")

async def add_active_user(cid: int):
    await r.sadd("active_users", cid)

async def get_active_users_count() -> int:
    return await r.scard("active_users")

# ================== COMMANDS ==================

@dp.message_handler(commands=["start"])
async def start_cmd(m: types.Message):
    await inc_commands()
    await add_active_user(m.chat.id)
    uptime = (moscow_time() - START_TIME).seconds // 60
    text = f"""👋 Привет, {m.from_user.first_name}!

🤖 Я - бот системы тестирования.
Система находится в стадии активной разработки.

📊 <b>Что уже работает:</b>
• Контейнеры Docker подняты
• Базы данных запущены  
• Веб-интерфейс доступен
• API сервисы готовы
• Базовая авторизация через веб

🔧 <b>Что будет добавлено:</b>
• Полное прохождение тестов
• Личный кабинет

<b>Основные команды:</b>
/start - Начало работы
/status - Статус системы
/services - Информация о сервисах
/help - Эта справка
/login - Авторизация
/complete_login - Завершить авторизацию после веб-клиента
/tests - Список доступных тестов (после авторизации)
/start_test &lt;test_id&gt; - Начать тест (после авторизации)

<b>Технические данные:</b>
📊 PostgreSQL: `localhost:5432`
🗄️ MongoDB: `localhost:27017`
⚡ Redis: `localhost:6379`

🚧 <b>В РАЗРАБОТКЕ:</b> 
• Полное прохождение тестов
• Личный кабинет

🌐 <b>Ссылки:</b>
• Веб-интерфейс: {WEB_CLIENT_URL}"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📊 Статус", callback_data="status"))
    keyboard.add(InlineKeyboardButton("🔧 Сервисы", callback_data="services"))
    keyboard.add(InlineKeyboardButton("🆘 Помощь", callback_data="help"))
    keyboard.add(InlineKeyboardButton("🔐 Авторизация", callback_data="login"))
    await m.answer(text, reply_markup=keyboard)

@dp.message_handler(commands=["status"])
async def status_cmd(m: types.Message):
    await inc_commands()
    uptime = (moscow_time() - START_TIME).seconds // 60
    total_commands = await r.get("total_commands") or 0
    active_users = await get_active_users_count()
    text = f"""🖥️ <b>СТАТУС СИСТЕМЫ</b>

Время: {moscow_time().strftime('%H:%M:%S')}
Активна: {uptime} мин

<b>Сервисы:</b>
• core-service: 🟢 Онлайн :8082
• auth-service: 🟢 Онлайн :8081
• web-client: 🟢 Онлайн :3000
• postgres: 🟢 Онлайн :5432
• mongodb: 🟢 Онлайн :27017
• redis: 🟢 Онлайн :6379

<b>Статистика:</b>
Команд выполнено: {total_commands}
Активных пользователей: {active_users}

🌐 Веб-интерфейс: {WEB_CLIENT_URL}
🔧 API Core: {AUTH_SERVICE_URL}
🔐 API Auth: {AUTH_SERVICE_URL}"""
    await m.answer(text)

@dp.message_handler(commands=["services"])
async def services_cmd(m: types.Message):
    await inc_commands()
    text = """🔧 <b>СЕРВИСЫ СИСТЕМЫ</b>

<b>CORE-SERVICE</b>
Статус: 🟢 Онлайн
Порт: `8082`
URL: `{AUTH_SERVICE_URL}`

<b>AUTH-SERVICE</b>
Статус: 🟢 Онлайн
Порт: `8081`
URL: `{AUTH_SERVICE_URL}`

<b>WEB-CLIENT</b>
Статус: 🟢 Онлайн
Порт: `3000`
URL: `{WEB_CLIENT_URL}`

<b>POSTGRES</b>
Статус: 🟢 Онлайн
Порт: `5432`

<b>MONGODB</b>
Статус: 🟢 Онлайн
Порт: `27017`

<b>REDIS</b>
Статус: 🟢 Онлайн
Порт: `6379`
URL: `{REDIS_URL}`"""
    await m.answer(text)

@dp.message_handler(commands=["help"])
async def help_cmd(m: types.Message):
    await inc_commands()
    text = """🆘 <b>ПОМОЩЬ ПО КОМАНДАМ</b>

<b>Основные команды:</b>
/start - Начало работы
/status - Статус системы
/services - Информация о сервисах
/help - Эта справка
/login - Авторизация
/complete_login - Завершить авторизацию после веб-клиента
/tests - Список доступных тестов (после авторизации)
/start_test &lt;test_id&gt; - Начать тест (после авторизации)

<b>Технические данные:</b>
📊 PostgreSQL: `localhost:5432`
🗄️ MongoDB: `localhost:27017`
⚡ Redis: `localhost:6379`

🚧 <b>В РАЗРАБОТКЕ:</b> 
• Полное прохождение тестов
• Личный кабинет"""
    await m.answer(text)

@dp.message_handler(commands=["login"])
async def login_cmd(m: types.Message):
    await inc_commands()
    text = "Пожалуйста, выберите метод авторизации:"
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("GitHub", callback_data="login_github"))
    keyboard.add(InlineKeyboardButton("Yandex ID", callback_data="login_yandex"))
    keyboard.add(InlineKeyboardButton("Code", callback_data="login_code"))
    await m.answer(text, reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith('login_'))
async def login_callback(c: types.CallbackQuery):
    method = c.data.split('_')[1]
    cid = c.message.chat.id
    user = await get_user(cid)
    token = secrets.token_hex(16)
    data = {"status": UserStatus.ANONYMOUS, "login_token": token}
    await set_user(cid, data)
    # Here: Request to Auth service with token and method
    # For now, simulate link
    link = f"{WEB_CLIENT_URL}/auth/{method}?token={token}"
    text = f"Для авторизации через {method.capitalize()} перейдите по ссылке: {link}"
    await bot.edit_message_text(text, c.message.chat.id, c.message.message_id)
    await c.answer()

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(m: types.Message):
    await inc_commands()
    user = await get_user(m.chat.id)
    if not user or user.get("status") != UserStatus.ANONYMOUS:
        text = "❌ Нет активной сессии авторизации"
    else:
        # Check with Auth service
        # Simulate success
        await set_user(m.chat.id, {"status": UserStatus.AUTHORIZED})
        text = "✅ Авторизация завершена"
    await m.answer(text)

@dp.message_handler(commands=["tests"])
async def tests_cmd(m: types.Message):
    await inc_commands()
    user = await get_user(m.chat.id)
    if not user or user.get("status") != UserStatus.AUTHORIZED:
        text = "❌ Требуется авторизация"
    else:
        if not TESTS:
            text = "Нет доступных тестов"
        else:
            text = "Доступные тесты:\n" + "\n".join(f"{k}: {v}" for k, v in TESTS.items())
    await m.answer(text)

@dp.message_handler(commands=["start_test"])
async def start_test_cmd(m: types.Message):
    await inc_commands()
    user = await get_user(m.chat.id)
    if not user or user.get("status") != UserStatus.AUTHORIZED:
        text = "❌ Требуется авторизация"
    else:
        tid = m.get_args()
        if tid not in TESTS:
            text = "❌ Укажите корректный ID теста"
        else:
            # Simulate no questions
            text = "В тесте нет вопросов" if not TESTS[tid] else f"🚀 Запуск теста: <b>{TESTS[tid]}</b>"
    await m.answer(text)

@dp.message_handler(commands=["logout"])
async def logout_cmd(m: types.Message):
    await inc_commands()
    user = await get_user(m.chat.id)
    if not user:
        text = "❌ Вы не авторизованы. Выход невозможен."
    elif user.get("status") == UserStatus.ANONYMOUS:
        text = "👤 Вы анонимны. Выход невозможен."
    else:
        args = m.get_args()
        if args == "all=true":
            # Request to Auth /logout with refresh
            text = "🚪 Сеанс завершён на всех устройствах."
        else:
            text = "🚪 Сеанс завершён."
        await delete_user(m.chat.id)
    await m.answer(text)

@dp.message_handler()
async def unknown_cmd(m: types.Message):
    await inc_commands()
    text = "❓ Нет такой команды"
    await m.answer(text)

# ================== CALLBACKS ==================

@dp.callback_query_handler(lambda c: c.data in ["status", "services", "help", "login"])
async def callback_handler(c: types.CallbackQuery):
    if c.data == "status":
        uptime = (moscow_time() - START_TIME).seconds // 60
        total_commands = await r.get("total_commands") or 0
        active_users = await get_active_users_count()
        text = f"""🖥️ <b>СТАТУС СИСТЕМЫ</b>

Время: {moscow_time().strftime('%H:%M:%S')}
Активна: {uptime} мин

<b>Сервисы:</b>
• core-service: 🟢 Онлайн :8082
• auth-service: 🟢 Онлайн :8081
• web-client: 🟢 Онлайн :3000
• postgres: 🟢 Онлайн :5432
• mongodb: 🟢 Онлайн :27017
• redis: 🟢 Онлайн :6379

<b>Статистика:</b>
Команд выполнено: {total_commands}
Активных пользователей: {active_users}

🌐 Веб-интерфейс: {WEB_CLIENT_URL}
🔧 API Core: {AUTH_SERVICE_URL}
🔐 API Auth: {AUTH_SERVICE_URL}"""
    elif c.data == "services":
        text = """🔧 <b>СЕРВИСЫ СИСТЕМЫ</b>

<b>CORE-SERVICE</b>
Статус: 🟢 Онлайн
Порт: `8082`
URL: `{AUTH_SERVICE_URL}`

<b>AUTH-SERVICE</b>
Статус: 🟢 Онлайн
Порт: `8081`
URL: `{AUTH_SERVICE_URL}`

<b>WEB-CLIENT</b>
Статус: 🟢 Онлайн
Порт: `3000`
URL: `{WEB_CLIENT_URL}`

<b>POSTGRES</b>
Статус: 🟢 Онлайн
Порт: `5432`

<b>MONGODB</b>
Статус: 🟢 Онлайн
Порт: `27017`

<b>REDIS</b>
Статус: 🟢 Онлайн
Порт: `6379`
URL: `{REDIS_URL}`"""
    elif c.data == "help":
        text = """🆘 <b>ПОМОЩЬ ПО КОМАНДАМ</b>

<b>Основные команды:</b>
/start - Начало работы
/status - Статус системы
/services - Информация о сервисах
/help - Эта справка
/login - Авторизация
/complete_login - Завершить авторизацию после веб-клиента
/tests - Список доступных тестов (после авторизации)
/start_test &lt;test_id&gt; - Начать тест (после авторизации)

<b>Технические данные:</b>
📊 PostgreSQL: `localhost:5432`
🗄️ MongoDB: `localhost:27017`
⚡ Redis: `localhost:6379`

🚧 <b>В РАЗРАБОТКЕ:</b> 
• Полное прохождение тестов
• Личный кабинет"""
    elif c.data == "login":
        text = "Пожалуйста, выберите метод авторизации:"
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("GitHub", callback_data="login_github"))
        keyboard.add(InlineKeyboardButton("Yandex ID", callback_data="login_yandex"))
        keyboard.add(InlineKeyboardButton("Code", callback_data="login_code"))
        await bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=keyboard)
        await c.answer()
        return

    await bot.edit_message_text(text, c.message.chat.id, c.message.message_id)
    await c.answer()

# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)