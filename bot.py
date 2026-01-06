import asyncio
import logging
import os
import json
from enum import Enum
from datetime import datetime

from aiogram.types import CallbackQuery
from aiogram import F
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ParseMode

import redis.asyncio as redis
from dotenv import load_dotenv

# ---------- ENV ----------

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "")
CORE_SERVICE_URL = os.getenv("CORE_SERVICE_URL", "")
WEB_CLIENT_URL = os.getenv("WEB_CLIENT_URL", "https://localhost:3000")


# ---------- LOGGING ----------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("telegram-client")


# ---------- BOT ----------

dp = Dispatcher()


# ---------- REDIS ----------

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True,
)


# ---------- USER STATUS ----------

class UserStatus(str, Enum):
    UNKNOWN = "unknown"
    ANONYMOUS = "anonymous"
    AUTHORIZED = "authorized"


# ---------- MARKDOWN V2 ----------

MD_V2_SPECIALS = r"_*[]()~`>#+-=|{}.!"

def md(text: str) -> str:
    for ch in MD_V2_SPECIALS:
        text = text.replace(ch, f"\\{ch}")
    return text


# ---------- REDIS HELPERS ----------

async def get_user(chat_id: int) -> dict | None:
    data = await redis_client.get(f"user:{chat_id}")
    return json.loads(data) if data else None


async def set_user(chat_id: int, data: dict):
    await redis_client.set(f"user:{chat_id}", json.dumps(data))


async def delete_user(chat_id: int):
    await redis_client.delete(f"user:{chat_id}")


async def get_status(chat_id: int) -> UserStatus:
    user = await get_user(chat_id)
    if not user:
        return UserStatus.UNKNOWN
    return UserStatus(user.get("status", UserStatus.UNKNOWN))


# ---------- AUTH GUARD ----------

async def require_auth(message: Message) -> bool:
    user = await get_user(message.chat.id)

    if not user:
        await message.answer(md("❌ *Вы не авторизованы*"))
        return False

    if user.get("status") != UserStatus.AUTHORIZED:
        await message.answer(md("⏳ *Ожидание подтверждения авторизации*"))
        return False

    return True




# =========================
# COMMANDS
# =========================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    name = message.from_user.first_name or "пользователь"

    text = (
        f"👋 *Привет, {name}\\!*\\n\\n"
        "🤖 *Я — Telegram\\-клиент системы массового тестирования*\\n"
        "Система находится в стадии активной разработки\\.\\n\\n"
        "📊 *Что уже работает:*\\n"
        "• Контейнеры Docker подняты\\n"
        "• Redis / Postgres / Mongo запущены\\n"
        "• Core API доступен\\n"
        "• Auth API доступен\\n"
        "• Базовая авторизация через Web\\n\\n"
        "🚧 *Что будет добавлено:*\\n"
        "• Полное прохождение тестов\\n"
        "• Уведомления\\n"
        "• Расширенные роли пользователей\\n\\n"
        "📌 *Доступные команды:*\\n"
        "/start — Начало работы\\n"
        "/help — Справка по командам\\n"
        "/status — Статус системы и пользователя\\n"
        "/services — Информация о сервисах\\n\\n"
        "🧪 *Тестирование:*\\n"
        "/tests — Список тестов\\n"
        "/starttest <id> — Начать тест\\n\\n"
        "🌐 *Ссылки:*\\n"
        f"• Web\\-клиент: {WEB_CLIENT_URL}\\n"
        f"• Core API: {CORE_SERVICE_URL}\\n"
        f"• Auth API: {AUTH_SERVICE_URL}"
    )

    await message.answer(md(text))


@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "🆘 *Справка по командам*\\n\\n"
        "🚀 *Старт:*\\n"
        "/start — начало работы\\n\\n"
        "🔐 *Авторизация:*\\n"
        "/login — начать вход\\n"
        "/completelogin — завершить вход\\n"
        "/logout — выйти\\n"
        "/logout_all — выйти везде\\n\\n"
        "🧪 *Тестирование:*\\n"
        "/tests — список тестов\\n"
        "/starttest <id> — начать тест\\n\\n"
        "ℹ️ *Информация:*\\n"
        "/status — статус системы\\n"
        "/services — сервисы"
    )

    await message.answer(md(text))


@dp.message(Command("login"))
async def cmd_login(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 GitHub", url=f"{AUTH_SERVICE_URL}/github")],
        [InlineKeyboardButton(text="🟡 Яндекс", url=f"{AUTH_SERVICE_URL}/yandex")],
        [InlineKeyboardButton(text="🔢 Код", callback_data="login_code")],
    ])

    await message.answer(
        md("🔐 *Авторизация*\n\nВыберите способ входа:"),
        reply_markup=kb,
    )


@dp.message(Command("completelogin"))
async def cmd_completelogin(message: Message):
    user = await get_user(message.chat.id)

    # 1️⃣ Пользователь вообще не начинал вход
    if not user:
        await message.answer(
            md(
                "❌ *Ошибка авторизации\\*\n\n"
                "Вы не начинали процесс входа\\"
            )
        )
        return

    status = UserStatus(user.get("status"))

    # 2️⃣ Уже авторизован
    if status == UserStatus.AUTHORIZED:
        await message.answer(
            md("ℹ️ *Вы уже авторизованы*")
        )
        return

    # 3️⃣ Не в состоянии ожидания
    if status != UserStatus.ANONYMOUS:
        await message.answer(
            md(
                "⏳ *Ожидание подтверждения*\n\n"
                "Завершите вход через /login"
            )
        )
        return

    # 4️⃣ Всё корректно — завершаем вход
    await set_user(
        message.chat.id,
        {
            "status": UserStatus.AUTHORIZED,
            "authorized_at": datetime.utcnow().isoformat(),
        },
    )

    await message.answer(
        md("✅ *Авторизация успешно завершена*")
    )


@dp.message(Command("logout"))
async def cmd_logout(message: Message):
    if not await require_auth(message):
        return

    await delete_user(message.chat.id)
    await message.answer(md("🚪 *Вы вышли из системы*"))




@dp.message(Command("logout_all"))
async def cmd_logout_all(message: Message):
    if not await require_auth(message):
        return

    await delete_user(message.chat.id)
    await message.answer(md("🚨 *Вы вышли со всех сессий*"))



@dp.message(Command("status"))
async def cmd_status(message: Message):
    status = await get_status(message.chat.id)

    text = (
        "📊 *СТАТУС СИСТЕМЫ*\\n\\n"
        f"👤 Пользователь: *{message.from_user.first_name}*\\n"
        f"🔐 Статус: *{status}*\\n\\n"
        "🟢 *Сервисы:*\\n"
        "• core\\-service — Онлайн :8082\\n"
        "• auth\\-service — Онлайн :8081\\n"
        "• web\\-client — Онлайн :3000\\n"
        "• postgres — Онлайн :5432\\n"
        "• mongodb — Онлайн :27017\\n"
        "• redis — Онлайн :6379"
    )

    await message.answer(md(text))


@dp.message(Command("services"))
async def cmd_services(message: Message):
    text = (
        "🧩 *СЕРВИСЫ*\\n\\n"
        "⚙️ *core\\-service*\\n"
        "— API логики тестирования\\n\\n"
        "🔐 *auth\\-service*\\n"
        "— Авторизация пользователей\\n\\n"
        "🌐 *web\\-client*\\n"
        "— Пользовательский интерфейс\\n\\n"
        "🗄 *postgres*\\n"
        "— Основная БД\\n\\n"
        "📦 *mongodb*\\n"
        "— Хранилище тестов\\n\\n"
        "⚡ *redis*\\n"
        "— Кэш и сессии"
    )

    await message.answer(md(text))


@dp.message(Command("tests"))
async def cmd_tests(message: Message):
    if not await require_auth(message):
        return

    tests = await get_user_tests(message.chat.id)  # ⬅️ из БД

    passed = [t for t in tests if t["passed"]]
    available = [t for t in tests if not t["passed"]]

    text = "📊 *Результаты тестирования:*\n\n"

    if passed:
        text += "✅ *Пройденные тесты:*\n"
        for t in passed:
            text += f"• {t['name']} — *{t['score']}/10*\n"
        text += "\n"
    else:
        text += "❌ *Вы ещё не прошли ни одного теста*\n\n"

    if available:
        text += "🟢 *Доступные тесты:*\n"
        for t in available:
            text += f"• {t['name']}\n"
    else:
        text += "🎉 *Все тесты пройдены!*"

    await message.answer(md(text))



@dp.message(Command("starttest"))
async def cmd_starttest(message: Message):
    if not await require_auth(message):
        return

    tests = await get_user_tests(message.chat.id)
    available = [t for t in tests if not t["passed"]]

    if not available:
        await message.answer(
            md("🎉 *У вас нет доступных тестов для прохождения*")
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🧪 {t['name']}",
                    callback_data=f"starttest:{t['id']}"
                )
            ]
            for t in available
        ]
    )

    await message.answer(
        md("🧪 *Выберите тест для прохождения:*"),
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("starttest_"))
async def cb_starttest(callback: CallbackQuery):
    if not await require_auth(callback.message):
        await callback.answer()
        return

    parts = callback.data.split(":")
    if len(parts) != 2 or not parts[1].isdigit():
        await callback.answer(text=md("Ошибка данных"), show_alert=True)

        return

    test_id = int(parts[1])

    await callback.answer()
    await callback.message.answer(
        md(f"▶️ *Тест {test_id} запущен*")
    )



# =========================
# MAIN
# =========================

async def main():
    logger.info("🤖 Telegram bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
