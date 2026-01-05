import os
import time
from enum import Enum
from datetime import datetime, timezone, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv
import redis.asyncio as redis

# ================= ENV =================

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ================= TIME =================

MSK = timezone(timedelta(hours=3))

def now_msk():
    return datetime.now(MSK)

START_TIME = now_msk()

# ================= INIT =================

bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
r = redis.from_url(REDIS_URL, decode_responses=True)

# ================= MODELS =================

class Status(str, Enum):
    UNKNOWN = "UNKNOWN"
    ANONYMOUS = "ANONYMOUS"
    AUTHORIZED = "AUTHORIZED"

def user_key(cid: int) -> str:
    return f"user:{cid}"

# ================= MOCK AUTH =================
# Заглушка Auth-сервиса

async def auth_check(login_token: str):
    # имитация: если токен заканчивается на 7 — успех
    if login_token.endswith("7"):
        return {
            "result": "success",
            "access": "ACCESS_TOKEN",
            "refresh": "REFRESH_TOKEN"
        }
    return {"result": "pending"}

# ================= HELPERS =================

async def inc_commands():
    await r.incr("stats:commands")

async def get_user(cid: int) -> dict:
    return await r.hgetall(user_key(cid))

async def set_user(cid: int, data: dict):
    await r.hset(user_key(cid), mapping=data)

async def delete_user(cid: int):
    await r.delete(user_key(cid))

async def active_users():
    keys = await r.keys("user:*")
    count = 0
    for k in keys:
        if await r.hget(k, "status") == Status.AUTHORIZED:
            count += 1
    return count

# ================= COMMANDS =================

@dp.message_handler(commands=["start"])
async def start_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        f"👋 <b>Привет, {m.from_user.first_name}!</b>\n\n"
        "🤖 Я — бот системы тестирования.\n"
        "Система находится в стадии активной разработки.\n\n"
        "📋 <b>Основные команды:</b>\n"
        "/start — начало работы\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/help — помощь\n"
        "/login — авторизация\n"
        "/complete_login — завершить авторизацию\n"
        "/logout — выход\n"
        "/tests — список тестов\n"
        "/start_test — начать тест"
    )

@dp.message_handler(commands=["help"])
async def help_cmd(m: types.Message):
    await inc_commands()
    await m.answer(
        "🆘 <b>ПОМОЩЬ</b>\n\n"
        "/start — начало\n"
        "/status — статус системы\n"
        "/services — сервисы\n"
        "/help — помощь\n"
        "/login — авторизация\n"
        "/complete_login — завершить авторизацию\n"
        "/logout — выход\n"
        "/tests — список тестов\n"
        "/start_test — начать тест"
    )

@dp.message_handler(commands=["login"])
async def login_cmd(m: types.Message):
    await inc_commands()
    cid = m.chat.id
    user = await get_user(cid)

    if user.get("status") == Status.AUTHORIZED:
        return await m.answer("✅ Вы уже авторизованы")

    token = str(int(time.time()))[-6:]

    await set_user(cid, {
        "status": Status.ANONYMOUS,
        "login_token": token,
        "ts": str(time.time())
    })

    await m.answer(
        "🔐 <b>АВТОРИЗАЦИЯ</b>\n\n"
        "Введите код в веб-клиенте:\n"
        f"<code>{token}</code>\n\n"
        "После подтверждения на сайте выполните команду:\n"
        "/complete_login"
    )

@dp.message_handler(commands=["complete_login"])
async def complete_login_cmd(m: types.Message):
    await inc_commands()
    cid = m.chat.id
    user = await get_user(cid)

    if not user or user.get("status") != Status.ANONYMOUS:
        return await m.answer("❌ Авторизация не начата")

    result = await auth_check(user["login_token"])

    if result["result"] == "pending":
        return await m.answer("⏳ Авторизация ещё не подтверждена")

    await set_user(cid, {
        "status": Status.AUTHORIZED,
        "access_token": result["access"],
        "refresh_token": result["refresh"]
    })

    await m.answer("✅ <b>АВТОРИЗАЦИЯ УСПЕШНА</b>")

@dp.message_handler(commands=["logout"])
async def logout_cmd(m: types.Message):
    await inc_commands()
    cid = m.chat.id
    user = await get_user(cid)

    if not user or user.get("status") in (Status.UNKNOWN, Status.ANONYMOUS):
        return await m.answer("ℹ️ Пользователь не авторизован")

    await delete_user(cid)
    await m.answer("📄 Сеанс завершён")

@dp.message_handler()
async def unknown_cmd(m: types.Message):
    await inc_commands()
    await m.answer("❓ Нет такой команды")

# ================= RUN =================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
