import os
import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
import uuid
import json

import redis.asyncio as redis
import aiohttp

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup

from dotenv import load_dotenv

# =====================================
# ENV
# =====================================

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

    AUTH_MODULE_URL = os.getenv("AUTH_MODULE_URL", "http://auth:8000")
    CORE_MODULE_URL = os.getenv("CORE_MODULE_URL", "http://core:8000")

    LOGIN_TTL_SECONDS = 300

if not Config.BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

# =====================================
# LOGGING
# =====================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("telegram-client")

# =====================================
# BOT INIT
# =====================================

bot = Bot(
    token=Config.BOT_TOKEN,
    parse_mode=ParseMode.MARKDOWN_V2,  # 🔥 ВАЖНО
)

dp = Dispatcher(storage=MemoryStorage())

# =====================================
# REDIS
# =====================================

redis_client: redis.Redis = redis.from_url(
    Config.REDIS_URL,
    decode_responses=True
)

# =====================================
# USER STATUSES (ПО ТЗ)
# =====================================

class UserStatus:
    UNKNOWN = "UNKNOWN"        # нет записи в Redis
    ANONYMOUS = "ANONYMOUS"    # есть login_token
    AUTHORIZED = "AUTHORIZED" # есть access + refresh

# =====================================
# MARKDOWN V2 ESCAPE
# =====================================

def md_escape(text: str) -> str:
    """
    Экранирование для MarkdownV2
    """
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in escape_chars else c for c in text)
# =====================================
# PART 2 — REDIS REPOSITORY / USER STATE
# =====================================


class UserRepository:
    """
    Хранилище состояния пользователя в Redis
    key   -> chat_id
    value -> JSON
    """

    @staticmethod
    async def get(chat_id: int) -> Optional[Dict[str, Any]]:
        data = await redis_client.get(str(chat_id))
        if not data:
            return None
        return json.loads(data)

    @staticmethod
    async def save(chat_id: int, payload: Dict[str, Any]) -> None:
        await redis_client.set(
            str(chat_id),
            json.dumps(payload),
        )

    @staticmethod
    async def delete(chat_id: int) -> None:
        await redis_client.delete(str(chat_id))


# =====================================
# USER STATE HELPERS
# =====================================

async def get_user_status(chat_id: int) -> str:
    """
    Возвращает статус пользователя:
    UNKNOWN | ANONYMOUS | AUTHORIZED
    """
    user = await UserRepository.get(chat_id)
    if not user:
        return UserStatus.UNKNOWN
    return user.get("status", UserStatus.UNKNOWN)


async def create_anonymous_user(chat_id: int) -> str:
    """
    Создание анонимного пользователя + login_token
    """
    login_token = str(uuid.uuid4())

    payload = {
        "status": UserStatus.ANONYMOUS,
        "login_token": login_token,
        "created_at": datetime.utcnow().isoformat(),
    }

    await UserRepository.save(chat_id, payload)
    return login_token


async def update_login_token(chat_id: int) -> str:
    """
    Обновление login_token для ANONYMOUS пользователя
    """
    login_token = str(uuid.uuid4())
    user = await UserRepository.get(chat_id)

    if not user:
        return await create_anonymous_user(chat_id)

    user["login_token"] = login_token
    user["status"] = UserStatus.ANONYMOUS
    await UserRepository.save(chat_id, user)
    return login_token


async def authorize_user(
    chat_id: int,
    access_token: str,
    refresh_token: str,
) -> None:
    """
    Перевод пользователя в AUTHORIZED
    """
    payload = {
        "status": UserStatus.AUTHORIZED,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "authorized_at": datetime.utcnow().isoformat(),
    }

    await UserRepository.save(chat_id, payload)


async def logout_user(chat_id: int) -> None:
    """
    Локальный logout (текущий chat_id)
    """
    await UserRepository.delete(chat_id)


# =====================================
# AUTH MODULE — STUBS (ПО ТЗ)
# =====================================

async def auth_check_login_token(login_token: str) -> Dict[str, Any]:
    """
    Заглушка модуля авторизации.
    В будущем: HTTP запрос в Auth Module
    """

    # 🔧 Пока что всегда "ожидание подтверждения"
    return {
        "status": "PENDING",  # PENDING | DENIED | APPROVED
    }


async def auth_exchange_token(login_token: str) -> Optional[Dict[str, str]]:
    """
    Обмен login_token на access/refresh
    """

    # 🔧 Заглушка: эмулируем успешный вход
    return {
        "access_token": f"access-{uuid.uuid4()}",
        "refresh_token": f"refresh-{uuid.uuid4()}",
    }


async def auth_logout_all(refresh_token: str) -> None:
    """
    Logout со всех устройств (stub)
    """
    return

# =====================================
# PART 2 — REDIS REPOSITORY / USER STATE
# =====================================


class UserRepository:
    """
    Хранилище состояния пользователя в Redis
    key   -> chat_id
    value -> JSON
    """

    @staticmethod
    async def get(chat_id: int) -> Optional[Dict[str, Any]]:
        data = await redis_client.get(str(chat_id))
        if not data:
            return None
        return json.loads(data)

    @staticmethod
    async def save(chat_id: int, payload: Dict[str, Any]) -> None:
        await redis_client.set(
            str(chat_id),
            json.dumps(payload),
        )

    @staticmethod
    async def delete(chat_id: int) -> None:
        await redis_client.delete(str(chat_id))


# =====================================
# USER STATE HELPERS
# =====================================

async def get_user_status(chat_id: int) -> str:
    """
    Возвращает статус пользователя:
    UNKNOWN | ANONYMOUS | AUTHORIZED
    """
    user = await UserRepository.get(chat_id)
    if not user:
        return UserStatus.UNKNOWN
    return user.get("status", UserStatus.UNKNOWN)


async def create_anonymous_user(chat_id: int) -> str:
    """
    Создание анонимного пользователя + login_token
    """
    login_token = str(uuid.uuid4())

    payload = {
        "status": UserStatus.ANONYMOUS,
        "login_token": login_token,
        "created_at": datetime.utcnow().isoformat(),
    }

    await UserRepository.save(chat_id, payload)
    return login_token


async def update_login_token(chat_id: int) -> str:
    """
    Обновление login_token для ANONYMOUS пользователя
    """
    login_token = str(uuid.uuid4())
    user = await UserRepository.get(chat_id)

    if not user:
        return await create_anonymous_user(chat_id)

    user["login_token"] = login_token
    user["status"] = UserStatus.ANONYMOUS
    await UserRepository.save(chat_id, user)
    return login_token


async def authorize_user(
    chat_id: int,
    access_token: str,
    refresh_token: str,
) -> None:
    """
    Перевод пользователя в AUTHORIZED
    """
    payload = {
        "status": UserStatus.AUTHORIZED,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "authorized_at": datetime.utcnow().isoformat(),
    }

    await UserRepository.save(chat_id, payload)


async def logout_user(chat_id: int) -> None:
    """
    Локальный logout (текущий chat_id)
    """
    await UserRepository.delete(chat_id)


# =====================================
# AUTH MODULE — STUBS (ПО ТЗ)
# =====================================

async def auth_check_login_token(login_token: str) -> Dict[str, Any]:
    """
    Заглушка модуля авторизации.
    В будущем: HTTP запрос в Auth Module
    """

    # 🔧 Пока что всегда "ожидание подтверждения"
    return {
        "status": "PENDING",  # PENDING | DENIED | APPROVED
    }


async def auth_exchange_token(login_token: str) -> Optional[Dict[str, str]]:
    """
    Обмен login_token на access/refresh
    """

    # 🔧 Заглушка: эмулируем успешный вход
    return {
        "access_token": f"access-{uuid.uuid4()}",
        "refresh_token": f"refresh-{uuid.uuid4()}",
    }


async def auth_logout_all(refresh_token: str) -> None:
    """
    Logout со всех устройств (stub)
    """
    return

# =====================================
# PART 3 — TELEGRAM HANDLERS (FINAL)
# =====================================


# ---------- UI HELPERS ----------

def build_login_keyboard(login_token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🐙 GitHub",
                    url=f"https://example.com/auth/github?token={login_token}",
                ),
                InlineKeyboardButton(
                    text="🟡 Яндекс ID",
                    url=f"https://example.com/auth/yandex?token={login_token}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔑 Войти по коду",
                    callback_data="login_by_code",
                )
            ],
        ]
    )


def build_tests_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🐍 Python", callback_data="test_python")],
            [InlineKeyboardButton(text="⚙️ DevOps", callback_data="test_devops")],
            [InlineKeyboardButton(text="🗄 Базы данных", callback_data="test_db")],
        ]
    )


def msg_not_logged() -> str:
    return md_escape("❗ Вы не авторизованы\\. Выполните /login")


def msg_already_logged() -> str:
    return md_escape("✅ Вы уже авторизованы")


# ---------- START ----------

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        md_escape(
            "👋 *Добро пожаловать!*\n\n"
            "Этот Telegram\\-бот предназначен для:\n"
            "• прохождения тестов\n"
            "• участия в опросах\n"
            "• получения уведомлений\n\n"
            "➡️ Используйте /login для входа\n"
            "➡️ /help — список команд"
        )
    )


# ---------- HELP ----------

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        md_escape(
            "📖 *Доступные команды:*\n\n"
            "/start — старт\n"
            "/login — авторизация\n"
            "/completelogin — завершить вход\n"
            "/tests — список тестов\n"
            "/starttest — начать тест\n"
            "/services — сервисы\n"
            "/status — статус входа\n"
            "/logout — выход"
        )
    )


# ---------- STATUS ----------

@dp.message(Command("status"))
async def status_cmd(message: types.Message):
    status = await get_user_status(message.chat.id)

    mapping = {
        UserStatus.UNKNOWN: "ℹ️ Статус: неизвестный пользователь",
        UserStatus.ANONYMOUS: "⏳ Статус: ожидается подтверждение входа",
        UserStatus.AUTHORIZED: "✅ Статус: авторизован",
    }

    await message.answer(md_escape(mapping[status]))


# ---------- LOGIN FLOW ----------

@dp.message(Command("login"))
async def login_cmd(message: types.Message):
    chat_id = message.chat.id
    status = await get_user_status(chat_id)

    if status == UserStatus.AUTHORIZED:
        await message.answer(msg_already_logged())
        return

    login_token = await update_login_token(chat_id)

    await message.answer(
        md_escape(
            "🔐 *Авторизация*\n\n"
            "Выберите способ входа:"
        ),
        reply_markup=build_login_keyboard(login_token),
    )


@dp.message(Command("completelogin"))
async def complete_login_cmd(message: types.Message):
    chat_id = message.chat.id
    user = await UserRepository.get(chat_id)

    if not user or user.get("status") != UserStatus.ANONYMOUS:
        await message.answer(msg_not_logged())
        return

    result = await auth_check_login_token(user["login_token"])

    if result["status"] == "PENDING":
        await message.answer(md_escape("⏳ Ожидается подтверждение входа"))
        return

    if result["status"] == "DENIED":
        await logout_user(chat_id)
        await message.answer(md_escape("❌ Авторизация отклонена"))
        return

    tokens = await auth_exchange_token(user["login_token"])
    await authorize_user(chat_id, tokens["access_token"], tokens["refresh_token"])

    await message.answer(md_escape("🎉 Авторизация успешно завершена"))


# ---------- LOGOUT ----------

@dp.message(Command("logout"))
async def logout_cmd(message: types.Message):
    await logout_user(message.chat.id)
    await message.answer(md_escape("🚪 Сеанс завершён"))


# ---------- AUTH CHECK ----------

async def require_auth(message: types.Message) -> bool:
    if await get_user_status(message.chat.id) != UserStatus.AUTHORIZED:
        await message.answer(msg_not_logged())
        return False
    return True


# ---------- TESTS ----------

@dp.message(Command("tests"))
async def tests_cmd(message: types.Message):
    if not await require_auth(message):
        return

    await message.answer(
        md_escape("📝 *Доступные тесты:*"),
        reply_markup=build_tests_keyboard(),
    )


@dp.message(Command("starttest"))
async def starttest_cmd(message: types.Message):
    if not await require_auth(message):
        return

    await message.answer(
        md_escape(
            "🚀 *Начать тест*\n\n"
            "Выберите тест:"
        ),
        reply_markup=build_tests_keyboard(),
    )


# ---------- SERVICES ----------

@dp.message(Command("services"))
async def services_cmd(message: types.Message):
    if not await require_auth(message):
        return

    await message.answer(
        md_escape(
            "🛠 *Сервисы:*\n\n"
            "• Управление тестами\n"
            "• История прохождений\n"
            "• Уведомления"
        )
    )


# ---------- FALLBACK ----------

@dp.message()
async def unknown_cmd(message: types.Message):
    await message.answer(md_escape("❌ Нет такой команды\\. Используйте /help"))

# =====================================
# PART 4 — CALLBACKS / BACKGROUND / RUN
# =====================================

from aiogram.types import CallbackQuery


# ---------- CALLBACKS (TEST SELECTION) ----------

@dp.callback_query(lambda c: c.data.startswith("test_"))
async def test_selected(callback: CallbackQuery):
    if await get_user_status(callback.message.chat.id) != UserStatus.AUTHORIZED:
        await callback.message.answer(md_escape("❗ Требуется авторизация"))
        await callback.answer()
        return

    test_map = {
        "test_python": "🐍 Python",
        "test_devops": "⚙️ DevOps",
        "test_db": "🗄 Базы данных",
    }

    test_name = test_map.get(callback.data, "Неизвестный тест")

    await callback.message.answer(
        md_escape(
            f"📝 *Вы выбрали тест:*\n\n"
            f"{test_name}\n\n"
            "🚀 Логика прохождения теста будет реализована в Core модуле."
        )
    )

    await callback.answer()


# ---------- CALLBACK (LOGIN BY CODE STUB) ----------

@dp.callback_query(lambda c: c.data == "login_by_code")
async def login_by_code(callback: CallbackQuery):
    await callback.message.answer(
        md_escape(
            "🔑 *Вход по коду*\n\n"
            "Функционал будет реализован позже."
        )
    )
    await callback.answer()


# ---------- BACKGROUND TASKS (STUBS ПО ТЗ) ----------

async def background_check_anonymous():
    """
    Проверка ANONYMOUS пользователей
    """
    while True:
        try:
            # 🔧 Заглушка — логика будет через Auth Module
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Anonymous check error: {e}")


async def background_check_notifications():
    """
    Проверка уведомлений AUTHORIZED пользователей
    """
    while True:
        try:
            # 🔧 Заглушка — логика будет через Core Module
            await asyncio.sleep(15)
        except Exception as e:
            logger.error(f"Notification check error: {e}")


# ---------- STARTUP / SHUTDOWN ----------

async def on_startup():
    logger.info("🤖 Telegram bot started")

    asyncio.create_task(background_check_anonymous())
    asyncio.create_task(background_check_notifications())


async def on_shutdown():
    logger.info("🛑 Telegram bot stopped")
    await redis_client.close()
    await bot.session.close()


# ---------- MAIN ----------

async def main():
    await on_startup()
    try:
        await dp.start_polling(bot)
    finally:
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())