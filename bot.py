import asyncio
import logging
import os
import json
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from functools import wraps

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest, TelegramRetryAfter

import redis.asyncio as redis
from dotenv import load_dotenv

# =========================
# ENV
# =========================
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("telegram-bot")

# =========================
# BOT
# =========================
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()


# =========================
# SIMPLE REDIS (без ошибок)
# =========================
class SimpleRedis:
    def __init__(self):
        self.data = {}
        self.connected = False

    async def connect(self):
        try:
            self.client = redis.from_url(REDIS_URL, decode_responses=True)
            await self.client.ping()
            self.connected = True
            logger.info("✅ Redis подключен")
        except Exception as e:
            logger.warning(f"⚠️ Redis недоступен: {e}. Используем локальное хранилище.")
            self.connected = False

    async def get(self, key: str) -> Optional[str]:
        if self.connected:
            try:
                return await self.client.get(key)
            except:
                pass
        return json.dumps(self.data.get(key)) if key in self.data else None

    async def setex(self, key: str, ttl: int, value: str):
        if self.connected:
            try:
                await self.client.setex(key, ttl, value)
                return
            except:
                pass
        self.data[key] = json.loads(value)

    async def delete(self, key: str):
        if self.connected:
            try:
                await self.client.delete(key)
            except:
                pass
        if key in self.data:
            del self.data[key]

    async def keys(self, pattern: str) -> List[str]:
        if self.connected:
            try:
                return await self.client.keys(pattern)
            except:
                pass
        pattern_re = pattern.replace('*', '.*')
        import re
        return [k for k in self.data.keys() if re.match(pattern_re, k)]


redis_client = SimpleRedis()


# =========================
# SIMPLE RATE LIMIT (без ошибок)
# =========================
async def check_rate_limit(chat_id: int, seconds: int = 2) -> bool:
    """Упрощенная проверка лимита запросов"""
    try:
        key = f"rate_limit:{chat_id}"
        now = datetime.utcnow().isoformat()

        # Получаем время последнего запроса
        last_time_str = await redis_client.get(key)

        if last_time_str:
            try:
                last_time = datetime.fromisoformat(json.loads(last_time_str))
                if (datetime.utcnow() - last_time).seconds < seconds:
                    return False
            except:
                pass

        # Сохраняем новое время
        await redis_client.setex(key, seconds, json.dumps(now))
        return True
    except Exception as e:
        logger.error(f"Rate limit error (ignored): {e}")
        return True  # При ошибке пропускаем проверку


def rate_limit(seconds: int = 2):
    """Декоратор для ограничения частоты запросов"""

    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            if not await check_rate_limit(message.chat.id, seconds):
                try:
                    await message.answer("⏳ <b>Слишком много запросов. Подождите немного.</b>")
                except:
                    pass
                return
            return await handler(message, *args, **kwargs)

        return wrapper

    return decorator


# =========================
# USER MANAGEMENT
# =========================
async def get_user(chat_id: int) -> Optional[Dict]:
    data = await redis_client.get(f"user:{chat_id}")
    return json.loads(data) if data else None


async def save_user(chat_id: int, data: Dict):
    await redis_client.setex(f"user:{chat_id}", 86400, json.dumps(data))


# =========================
# COMMAND HANDLERS
# =========================
@dp.message(Command("start"))
@rate_limit()
async def cmd_start(message: Message):
    """Обработчик /start"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user:
        text = f"""👋 <b>Добро пожаловать, {message.from_user.first_name or 'пользователь'}!</b>

🤖 <b>Telegram-бот системы тестирования</b>

Для начала работы используйте команду /login"""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔐 Авторизоваться", callback_data="login")]
        ])
    elif user.get("status") == "authorized":
        email = user.get("email", "пользователь")
        text = f"""✅ <b>Вы авторизованы как {email}</b>

<b>Доступные команды:</b>
/tests — список тестов
/courses — список дисциплин
/profile — ваш профиль
/logout — выход из системы

Используйте /help для полного списка команд."""
        kb = None
    else:
        text = """🔐 <b>Ожидание авторизации</b>

Вы начали процесс входа.
Используйте /login для повторной попытки."""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Авторизоваться", callback_data="login")]
        ])

    await message.answer(text, reply_markup=kb)


@dp.message(Command("help"))
@rate_limit()
async def cmd_help(message: Message):
    help_text = """🆘 <b>Справка по командам</b>

<b>Основные команды:</b>
/start — начало работы  
/help — эта справка  
/status — статус системы  

<b>Авторизация:</b>
/login — вход через код  
/logout — выход  

<b>Тестирование:</b>
/tests — список тестов  
/courses — список дисциплин  

<b>Профиль:</b>
/profile — информация о пользователе"""
    await message.answer(help_text)


@dp.message(Command("login"))
@rate_limit()
async def cmd_login(message: Message):
    """Упрощенная авторизация"""
    chat_id = message.chat.id

    # Имитируем успешную авторизацию
    await save_user(chat_id, {
        "status": "authorized",
        "email": f"user_{chat_id}@example.com",
        "user_id": f"user_{secrets.token_hex(8)}",
        "authorized_at": datetime.utcnow().isoformat()
    })

    await message.answer(f"""✅ <b>Авторизация успешна!</b>

Добро пожаловать, user_{chat_id}@example.com

Теперь доступны команды:
/tests — список тестов
/courses — список дисциплин""")


@dp.message(Command("logout"))
@rate_limit()
async def cmd_logout(message: Message):
    await redis_client.delete(f"user:{message.chat.id}")
    await message.answer("🚪 <b>Вы вышли из системы</b>")


@dp.message(Command("status"))
@rate_limit()
async def cmd_status(message: Message):
    user = await get_user(message.chat.id)
    status = "✅ Авторизован" if user and user.get("status") == "authorized" else "❌ Не авторизован"

    text = f"""📊 <b>Статус системы</b>

<b>Ваш статус:</b> {status}
<b>Redis:</b> {"🟢 онлайн" if redis_client.connected else "🔴 оффлайн"}
<b>Bot:</b> 🟢 онлайн"""

    await message.answer(text)


@dp.message(Command("tests"))
@rate_limit()
async def cmd_tests(message: Message):
    user = await get_user(message.chat.id)
    if not user or user.get("status") != "authorized":
        await message.answer("❌ <b>Требуется авторизация</b>\n\nИспользуйте /login для входа.")
        return

    text = """📚 <b>Доступные тесты</b>

1. <b>Python Basics</b> (10 вопросов)
2. <b>Async IO</b> (8 вопросов)
3. <b>Docker</b> (12 вопросов)

Используйте /starttest <номер> для начала теста."""

    await message.answer(text)


@dp.message(Command("courses"))
@rate_limit()
async def cmd_courses(message: Message):
    user = await get_user(message.chat.id)
    if not user or user.get("status") != "authorized":
        await message.answer("❌ <b>Требуется авторизация</b>\n\nИспользуйте /login для входа.")
        return

    text = """🎓 <b>Доступные дисциплины</b>

1. <b>Программирование</b> - Основы программирования
2. <b>Базы данных</b> - SQL и NoSQL
3. <b>Сети</b> - Основы компьютерных сетей"""

    await message.answer(text)


@dp.message(Command("ping"))
@rate_limit()
async def cmd_ping(message: Message):
    await message.answer("🏓 <b>Pong!</b>\n\nБот работает корректно.")


@dp.message(Command("echo"))
@rate_limit()
async def cmd_echo(message: Message):
    text = message.text or ""
    if len(text) > 6:
        await message.answer(f"📢 <b>Эхо:</b> {text[6:]}")
    else:
        await message.answer("📢 <b>Напишите что-нибудь после /echo</b>")


# =========================
# CALLBACK HANDLERS
# =========================
@dp.callback_query(F.data == "login")
async def callback_login(callback: CallbackQuery):
    await callback.answer()
    await cmd_login(callback.message)


# =========================
# MAIN
# =========================
async def main():
    logger.info("🤖 Telegram bot starting...")

    # Подключаем Redis
    await redis_client.connect()

    logger.info("🚀 Bot is ready!")

    try:
        await dp.start_polling(bot, skip_updates=True)
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")


if __name__ == "__main__":
    asyncio.run(main())