import asyncio
import logging
import os
from enum import Enum

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery
import redis.asyncio as redis
from dotenv import load_dotenv
from aiogram.types import CallbackQuery
from datetime import datetime

# ---------- ENV ----------

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "")
CORE_SERVICE_URL = os.getenv("CORE_SERVICE_URL", "")
WEB_CLIENT_URL = os.getenv("WEB_CLIENT_URL", "")


# ---------- LOGGING ----------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("telegram-client")


# ---------- BOT ----------

bot = Bot(
    token=BOT_TOKEN,
    parse_mode=ParseMode.MARKDOWN_V2,  # ❗ ВАЖНО
)

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


# ---------- MARKDOWN V2 ESCAPE ----------

MD_V2_SPECIALS = r"_*[]()~`>#+-=|{}.!"

def md(text: str) -> str:
    """
    Безопасное экранирование MarkdownV2
    """
    for ch in MD_V2_SPECIALS:
        text = text.replace(ch, f"\\{ch}")
    return text


# ---------- REDIS HELPERS ----------

async def get_user(chat_id: int) -> dict | None:
    data = await redis_client.get(f"user:{chat_id}")
    return eval(data) if data else None


async def set_user(chat_id: int, data: dict):
    await redis_client.set(f"user:{chat_id}", str(data))


async def delete_user(chat_id: int):
    await redis_client.delete(f"user:{chat_id}")


async def get_status(chat_id: int) -> UserStatus:
    user = await get_user(chat_id)
    if not user:
        return UserStatus.UNKNOWN
    return UserStatus(user.get("status", UserStatus.UNKNOWN))


# ---------- AUTH GUARD ----------

async def require_auth(message: Message) -> bool:
    status = await get_status(message.chat.id)

    if status != UserStatus.AUTHORIZED:
        await message.answer(
            md(
                "🔐 *Вы не авторизованы*\n\n"
                "Используйте команду /login"
            )
        )
        return False

    return True

# =========================
# PART 2 — START / HELP / AUTH COMMANDS
# =========================


# ---------- KEYBOARDS ----------

def auth_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🐙 GitHub",
                    callback_data="login:github",
                ),
                InlineKeyboardButton(
                    text="🟡 Яндекс ID",
                    callback_data="login:yandex",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔢 Код",
                    callback_data="login:code",
                ),
            ],
        ]
    )


# ---------- /start ----------

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        md(
            "👋 *Привет\\!*\n\n"
            "🤖 *Telegram\\-клиент системы массового тестирования*\n"
            "Система находится в стадии активной разработки\\.\n\n"

            "📊 *Что уже работает:*\n"
            "• Docker\\-контейнеры запущены\n"
            "• Redis / Postgres / Mongo доступны\n"
            "• Core API готов\n"
            "• Auth API готов\n"
            "• Базовая авторизация через Web\n\n"

            "🛠 *Что будет добавлено:*\n"
            "• Полное прохождение тестов\n"
            "• Уведомления\n\n"

            "📌 *Основные команды:*\n"
            "/start — Начало работы\n"
            "/help — Справка\n"
            "/status — Статус системы\n"
            "/services — Сервисы\n\n"

            "🔐 *Авторизация:*\n"
            "/login — Вход\n"
            "/completelogin — Завершить вход\n"
            "/logout — Выход\n\n"

            "🧪 *Тестирование:*\n"
            "/tests — Список тестов\n"
            "/starttest <id> — Начать тест\n\n"

            "🌐 *Ссылки:*\n"
            f"• Web: {WEB_CLIENT_URL}\n"
            f"• Core API: {CORE_SERVICE_URL}\n"
            f"• Auth API: {AUTH_SERVICE_URL}"
        )
    )


# ---------- /help ----------

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        md(
            "🆘 *Справка*\n\n"
            "/start — Начало работы\n"
            "/status — Статус пользователя\n"
            "/services — Список сервисов\n\n"
            "/login — Авторизация\n"
            "/completelogin — Завершить вход\n"
            "/logout — Выход\n\n"
            "/tests — Доступные тесты\n"
            "/starttest <id> — Начать тест"
        )
    )


# ---------- /login ----------

@dp.message(Command("login"))
async def cmd_login(message: Message):
    status = await get_status(message.chat.id)

    if status == UserStatus.AUTHORIZED:
        await message.answer(
            md("✅ *Вы уже авторизованы*")
        )
        return

    await message.answer(
        md(
            "🔐 *Авторизация*\n\n"
            "Выберите способ входа:"
        ),
        reply_markup=auth_keyboard(),
    )


# ---------- /completelogin ----------

@dp.message(Command("completelogin"))
async def cmd_complete_login(message: Message):
    status = await get_status(message.chat.id)

    if status == UserStatus.AUTHORIZED:
        await message.answer(
            md("✅ *Вы уже авторизованы*")
        )
        return

    await message.answer(
        md(
            "⏳ *Завершение авторизации*\n\n"
            "Проверяем статус входа\\.\\.\\.\n"
            "_(модуль авторизации будет подключён позже)_"
        )
    )


# ---------- /logout ----------

@dp.message(Command("logout"))
async def cmd_logout(message: Message):
    await delete_user(message.chat.id)

    await message.answer(
        md(
            "🚪 *Вы вышли из системы*\n"
            "Статус сброшен"
        )
    )

# =========================
# PART 3 — STATUS / SERVICES / AUTH CALLBACKS
# =========================

# ---------- STATUS TEXT ----------

def status_text(status: UserStatus) -> str:
    if status == UserStatus.AUTHORIZED:
        return "🟢 *Авторизован*"
    if status == UserStatus.ANONYMOUS:
        return "🟡 *Гость*"
    return "⚪ *Неизвестный пользователь*"


# ---------- /status ----------

@dp.message(Command("status"))
async def cmd_status(message: Message):
    status = await get_status(message.chat.id)

    await message.answer(
        md(
            "📊 *СТАТУС СИСТЕМЫ*\n\n"
            f"👤 Пользователь: {status_text(status)}\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n\n"

            "📦 *Сервисы:*\n"
            "• core\\-service — 🟢 Онлайн\n"
            "• auth\\-service — 🟢 Онлайн\n"
            "• web\\-client — 🟢 Онлайн\n"
            "• postgres — 🟢 Онлайн\n"
            "• mongodb — 🟢 Онлайн\n"
            "• redis — 🟢 Онлайн\n\n"

            "📈 *Статистика:*\n"
            "Команд выполнено: 0\n"
            "Активных пользователей: 1\n\n"

            f"🌐 Web: {WEB_CLIENT_URL}\n"
            f"🔗 Core API: {CORE_SERVICE_URL}\n"
            f"🔐 Auth API: {AUTH_SERVICE_URL}"
        )
    )


# ---------- /services ----------

@dp.message(Command("services"))
async def cmd_services(message: Message):
    if not await require_auth(message):
        return

    await message.answer(
        md(
            "🧩 *СЕРВИСЫ*\n\n"
            "⚙️ core\\-service\n"
            "— API логики тестирования\n\n"

            "🔐 auth\\-service\n"
            "— Авторизация пользователей\n\n"

            "🌐 web\\-client\n"
            "— Пользовательский интерфейс\n\n"

            "🗄 postgres\n"
            "— Основная БД\n\n"

            "📦 mongodb\n"
            "— Хранилище тестов\n\n"

            "⚡ redis\n"
            "— Кэш и сессии"
        )
    )


# ---------- AUTH CALLBACKS ----------

@dp.callback_query(lambda c: c.data.startswith("login:"))
async def auth_callback(call: CallbackQuery):
    method = call.data.split(":")[1]

    user_data = {
        "status": UserStatus.ANONYMOUS,
        "auth_method": method,
        "created_at": datetime.utcnow().isoformat(),
    }

    await set_user(call.message.chat.id, user_data)

    if method == "github":
        text = "🐙 *GitHub авторизация*\n\nПерейдите в Web для входа"
    elif method == "yandex":
        text = "🟡 *Яндекс ID авторизация*\n\nПерейдите в Web для входа"
    else:
        text = "🔢 *Вход по коду*\n\nВведите код в Web интерфейсе"

    await call.message.answer(
        md(text + f"\n\n🌐 {WEB_CLIENT_URL}")
    )

    await call.answer()


# ---------- COMPLETE LOGIN (MOCK) ----------

async def complete_login(chat_id: int):
    await set_user(
        chat_id,
        {
            "status": UserStatus.AUTHORIZED,
            "authorized_at": datetime.utcnow().isoformat(),
        },
    )

# =========================
# PART 4 — TESTS / LOGOUT / RUN
# =========================

# ---------- MOCK TESTS ----------

TESTS = [
    {"id": "python_base", "title": "Python основы"},
    {"id": "docker_base", "title": "Docker основы"},
    {"id": "backend_junior", "title": "Backend Junior"},
]


# ---------- /tests ----------

@dp.message(Command("tests"))
async def tests_cmd(message: Message):
    if not await require_auth(message):
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🧪 {test['title']}",
                    callback_data=f"test:{test['id']}",
                )
            ]
            for test in TESTS
        ]
    )

    await message.answer(
        md(
            "🧪 *ДОСТУПНЫЕ ТЕСТЫ*\n\n"
            "Выберите тест для запуска:"
        ),
        reply_markup=keyboard,
    )


# ---------- /starttest ----------

@dp.message(Command("starttest"))
async def starttest_cmd(message: Message):
    if not await require_auth(message):
        return

    await message.answer(
        md(
            "▶️ *Запуск теста*\n\n"
            "Используйте команду /tests\n"
            "и выберите тест из списка"
        )
    )


# ---------- TEST CALLBACK ----------

@dp.callback_query(lambda c: c.data.startswith("test:"))
async def test_callback(call: CallbackQuery):
    test_id = call.data.split(":")[1]

    test = next((t for t in TESTS if t["id"] == test_id), None)
    if not test:
        await call.answer("Тест не найден", show_alert=True)
        return

    await call.message.answer(
        md(
            f"🚀 *Тест запущен*\n\n"
            f"📌 Название: {test['title']}\n\n"
            "⏳ Логика прохождения будет добавлена позже"
        )
    )

    await call.answer()


# ---------- /completelogin ----------

@dp.message(Command("completelogin"))
async def complete_login_cmd(message: Message):
    status = await get_status(message.chat.id)

    if status == UserStatus.AUTHORIZED:
        await message.answer(
            md("✅ *Вы уже авторизованы*")
        )
        return

    await set_user(
        message.chat.id,
        {
            "status": UserStatus.AUTHORIZED,
            "authorized_at": datetime.utcnow().isoformat(),
        },
    )

    await message.answer(
        md(
            "🎉 *Авторизация завершена*\n\n"
            "Теперь вам доступны тесты и сервисы"
        )
    )


# ---------- /logout ----------

@dp.message(Command("logout"))
async def logout_cmd(message: Message):
    status = await get_status(message.chat.id)

    if status == UserStatus.UNKNOWN:
        await message.answer(
            md("ℹ️ *Вы ещё не входили в систему*")
        )
        return

    await delete_user(message.chat.id)

    await message.answer(
        md("🔓 *Вы вышли из системы*")
    )


# ---------- MAIN ----------

async def main():
    logger.info("🤖 Telegram bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
