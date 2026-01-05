import os
import time
import asyncio
from enum import Enum

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

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
r = redis.from_url(REDIS_URL, decode_responses=True)

START_TIME = int(time.time())

LOGIN_TTL = 120  # 2 минуты

# =========================
# ENUMS
# =========================

class Status(str, Enum):
    UNKNOWN = "UNKNOWN"
    WAIT_LOGIN = "WAIT_LOGIN"
    AUTHORIZED = "AUTHORIZED"

# =========================
# REDIS HELPERS
# =========================

def ukey(cid): return f"user:{cid}"

async def get_user(cid):
    return await r.hgetall(ukey(cid))

async def save_user(cid, data):
    await r.hset(ukey(cid), mapping=data)

async def del_user(cid):
    await r.delete(ukey(cid))

# =========================
# METRICS
# =========================

async def inc_commands():
    await r.incr("stats:commands")

async def get_commands():
    v = await r.get("stats:commands")
    return int(v or 0)

async def active_users():
    keys = await r.keys("user:*")
    return len(keys)

# =========================
# COMMANDS
# =========================

@dp.message_handler(commands=["start"])
async def start_cmd(msg: types.Message):
    await inc_commands()
    await msg.answer(
        f"👋 <b>Привет, {msg.from_user.first_name}!</b>\n\n"
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
        "• Auth API: http://auth-service:8081"
    )

@dp.message_handler(commands=["status"])
async def status_cmd(msg: types.Message):
    await inc_commands()
    uptime = int((time.time() - START_TIME) / 60)
    await msg.answer(
        "📊 <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"Время (UTC): {time.strftime('%H:%M:%S', time.gmtime())}\n"
        f"Активна: {uptime} мин\n\n"
        "<b>Сервисы:</b>\n"
        "• core-service: 🟢 Онлайн :8082\n"
        "• auth-service: 🟢 Онлайн :8081\n"
        "• web-client: 🟢 Онлайн :3000\n"
        "• postgres: 🟢 Онлайн :5432\n"
        "• mongodb: 🟢 Онлайн :27017\n"
        "• redis: 🟢 Онлайн :6379\n\n"
        "<b>Статистика:</b>\n"
        f"Команд выполнено: {await get_commands()}\n"
        f"Активных пользователей: {await active_users()}"
    )

@dp.message_handler(commands=["services"])
async def services_cmd(msg):
    await inc_commands()
    await msg.answer(
        "🛠 <b>СЕРВИСЫ СИСТЕМЫ</b>\n\n"
        "<b>CORE-SERVICE</b>\nСтатус: 🟢 Онлайн\nПорт: 8082\n\n"
        "<b>AUTH-SERVICE</b>\nСтатус: 🟢 Онлайн\nПорт: 8081\n\n"
        "<b>WEB-CLIENT</b>\nСтатус: 🟢 Онлайн\nПорт: 3000\n\n"
        "POSTGRES — 5432\nMONGODB — 27017\nREDIS — 6379"
    )

@dp.message_handler(commands=["login"])
async def login_cmd(msg):
    await inc_commands()
    code = str(int(time.time()))[-6:]
    await save_user(msg.chat.id, {
        "status": Status.WAIT_LOGIN,
        "code": code,
        "ts": int(time.time())
    })
    await msg.answer(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        "Введите код в веб-клиенте:\n"
        f"<code>{code}</code>"
    )

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(msg):
    await inc_commands()
    user = await get_user(msg.chat.id)
    if not user or user.get("status") != Status.WAIT_LOGIN:
        await msg.answer("❌ Авторизация не начата. Используйте /login")
        return

    if int(time.time()) - int(user["ts"]) > LOGIN_TTL:
        await del_user(msg.chat.id)
        await msg.answer("❌ Время авторизации истекло")
        return

    await msg.answer("⏳ <b>ОЖИДАНИЕ ПОДТВЕРЖДЕНИЯ</b>\nЗавершите вход в веб-клиенте.")

@dp.message_handler(commands=["tests"])
async def tests_cmd(msg):
    await inc_commands()
    user = await get_user(msg.chat.id)
    if not user or user.get("status") != Status.AUTHORIZED:
        await msg.answer("❌ Требуется авторизация (/login)")
        return
    await msg.answer("🧪 <b>ТЕСТОВ НЕТ</b>\nВ данный момент тесты отсутствуют.")

@dp.message_handler(commands=["start_test"])
async def start_test_cmd(msg):
    await inc_commands()
    await msg.answer("❌ Нет доступных тестов")

@dp.message_handler()
async def unknown(msg):
    await msg.answer("❓ <b>Нет такой команды</b>")

# =========================
# MOCK AUTH WATCHER
# =========================

async def watcher():
    while True:
        for key in await r.keys("user:*"):
            u = await r.hgetall(key)
            if u.get("status") == Status.WAIT_LOGIN:
                if int(time.time()) - int(u["ts"]) > 15:
                    await r.hset(key, "status", Status.AUTHORIZED)
                    cid = int(key.split(":")[1])
                    await bot.send_message(cid, "✅ <b>АВТОРИЗАЦИЯ УСПЕШНА</b>")
        await asyncio.sleep(5)

async def on_startup(_):
    asyncio.create_task(watcher())

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)
