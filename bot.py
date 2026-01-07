import asyncio
import logging
import os
import json
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from functools import wraps
from enum import Enum

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode

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
# USER STATUS
# =========================
class UserStatus(str, Enum):
    UNKNOWN = "unknown"
    ANONYMOUS = "anonymous"
    AUTHORIZED = "authorized"


# =========================
# SIMPLE REDIS (без ошибок)
# =========================
class SimpleRedis:
    def __init__(self):
        self.data = {}
        self.connected = False

    async def connect(self):
        try:
            self.client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
            await self.client.ping()
            self.connected = True
            logger.info("✅ Redis подключен")
        except Exception as e:
            logger.warning(f"⚠️ Redis недоступен: {e}. Используем локальное хранилище.")
            self.connected = False

    async def get(self, key: str) -> Optional[str]:
        try:
            if self.connected:
                return await self.client.get(key)
        except:
            pass
        return json.dumps(self.data.get(key)) if key in self.data else None

    async def setex(self, key: str, ttl: int, value: str):
        try:
            if self.connected:
                await self.client.setex(key, ttl, value)
                return
        except:
            pass
        self.data[key] = json.loads(value)

    async def delete(self, key: str):
        try:
            if self.connected:
                await self.client.delete(key)
        except:
            pass
        if key in self.data:
            del self.data[key]

    async def keys(self, pattern: str) -> List[str]:
        try:
            if self.connected:
                return await self.client.keys(pattern)
        except:
            pass
        import re
        pattern_re = pattern.replace('*', '.*')
        return [k for k in self.data.keys() if re.match(pattern_re, k)]


redis_client = SimpleRedis()


# =========================
# AUTH SERVICE STUB (упрощенный)
# =========================
class AuthServiceStub:
    def __init__(self):
        self.login_tokens = {}
        self.codes = {}

    async def generate_login_url(self, login_token: str, provider: str = "code") -> str:
        code = secrets.randbelow(900000) + 100000
        self.codes[code] = login_token
        self.login_tokens[login_token] = {
            "status": "pending",
            "code": code,
            "created_at": datetime.utcnow()
        }
        return "https://t.me/cfutgbot"

    async def check_login_token(self, login_token: str) -> Optional[Dict]:
        if login_token not in self.login_tokens:
            return None

        token_data = self.login_tokens[login_token]

        # Автоматически подтверждаем через 1 секунду для тестирования
        if (datetime.utcnow() - token_data["created_at"]).seconds > 1:
            token_data["status"] = "granted"
            return {
                "status": "granted",
                "access_token": f"access_{secrets.token_hex(16)}",
                "refresh_token": f"refresh_{secrets.token_hex(16)}",
                "user": {
                    "id": f"user_{secrets.token_hex(8)}",
                    "email": f"user_{login_token[:8]}@example.com"
                }
            }

        return {"status": "pending"}


auth_service = AuthServiceStub()


# =========================
# RATE LIMIT (упрощенный, всегда разрешает)
# =========================
async def check_rate_limit(chat_id: int, seconds: int = 2) -> bool:
    """Упрощенная проверка - всегда разрешаем"""
    return True


def rate_limit(seconds: int = 2):
    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            return await handler(message, *args, **kwargs)

        return wrapper

    return decorator


def safe_send_message(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")

    return wrapper


# =========================
# USER MANAGEMENT
# =========================
async def get_user(chat_id: int) -> Optional[Dict]:
    data = await redis_client.get(f"user:{chat_id}")
    if data:
        return json.loads(data)
    return None


async def save_user(chat_id: int, data: Dict):
    await redis_client.setex(f"user:{chat_id}", 86400, json.dumps(data))


async def delete_user(chat_id: int):
    await redis_client.delete(f"user:{chat_id}")


async def set_user_anonymous(chat_id: int, login_token: str, provider: str = "code"):
    await save_user(chat_id, {
        "status": UserStatus.ANONYMOUS,
        "login_token": login_token,
        "provider": provider,
        "created_at": datetime.utcnow().isoformat()
    })


async def set_user_authorized(chat_id: int, access_token: str, refresh_token: str, user_id: str, email: str):
    await save_user(chat_id, {
        "status": UserStatus.AUTHORIZED,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user_id,
        "email": email,
        "authorized_at": datetime.utcnow().isoformat()
    })


async def get_user_status(chat_id: int) -> UserStatus:
    user = await get_user(chat_id)
    if not user:
        return UserStatus.UNKNOWN
    return UserStatus(user.get("status", UserStatus.UNKNOWN))


# =========================
# COMMAND HANDLERS - ВОССТАНАВЛИВАЕМ ОРИГИНАЛЬНУЮ ЛОГИКУ
# =========================
@dp.message(Command("start"))
@rate_limit()
@safe_send_message
async def cmd_start(message: Message):
    """Обработчик /start - ОРИГИНАЛЬНАЯ ЛОГИКА"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user:
        text = f"""
👋 <b>Добро пожаловать, {message.from_user.first_name or 'пользователь'}!</b>

🤖 <b>Telegram-клиент системы тестирования</b>

Для начала работы необходимо авторизоваться.

Используйте команду /login для входа в систему.
"""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔐 Авторизоваться", callback_data="login")]
        ])
    elif user.get("status") == UserStatus.ANONYMOUS:
        login_token = user.get("login_token", "")

        # Получаем код из заглушки
        code = ""
        if login_token in auth_service.login_tokens:
            token_data = auth_service.login_tokens[login_token]
            if "code" in token_data:
                code = token_data["code"]

        text = f"""
🔐 <b>Ожидание авторизации</b>

Вы начали процесс входа через code.
Для завершения авторизации введите код в веб-клиенте:

<b>Код: <code>{code}</code></b>

Или нажмите "Проверить статус".
"""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
            [InlineKeyboardButton(text="🔄 Начать заново", callback_data="login")]
        ])
    else:
        user_email = user.get("email", "пользователь")
        text = f"""
✅ <b>Вы авторизованы как {user_email}</b>

<b>Доступные команды:</b>
/tests — список тестов
/courses — список дисциплин
/profile — ваш профиль
/logout — выход из системы

Используйте /help для полного списка команд.
"""
        kb = None

    await message.answer(text, reply_markup=kb)


@dp.message(Command("help"))
@rate_limit()
@safe_send_message
async def cmd_help(message: Message):
    help_text = """
🆘 <b>Справка по командам</b>

<b>Основные команды:</b>
/start — начало работы  
/help — эта справка  
/status — статус системы  

<b>Авторизация:</b>
/login — вход через код  
/logout — выход  
/logout all=true — выход со всех устройств  

<b>Дисциплины и тесты:</b>
/courses — список дисциплин  
/tests — список тестов  

<b>Профиль:</b>
/profile — информация о пользователе  

<b>Технические команды:</b>
/services — информация о сервисах  
/debug — отладочная информация  
/ping — проверка работы бота
"""
    await message.answer(help_text)


@dp.message(Command("login"))
@rate_limit()
@safe_send_message
async def cmd_login(message: Message):
    """Обработчик /login"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    # Если уже авторизован
    if user and user.get("status") == UserStatus.AUTHORIZED:
        await message.answer(f"✅ <b>Вы уже авторизованы как {user.get('email')}</b>\n\nИспользуйте /logout для выхода.")
        return

    # Генерируем login_token
    login_token = secrets.token_urlsafe(32)
    provider = "code"

    # Устанавливаем пользователя как ANONYMOUS
    await set_user_anonymous(chat_id, login_token, provider)

    # Получаем URL для авторизации
    auth_url = await auth_service.generate_login_url(login_token, provider)

    # Получаем код из заглушки
    code = auth_service.login_tokens[login_token]["code"]

    text = f"""
🔐 <b>Авторизация через код</b>

Для входа в систему введите код в веб-клиенте:

<b>Код: <code>{code}</code></b>

⏳ <b>Код действителен 5 минут</b>

После ввода кода нажмите "Проверить статус".
"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await message.answer(text, reply_markup=kb)


@dp.message(Command("logout"))
@rate_limit()
@safe_send_message
async def cmd_logout(message: Message):
    """Обработчик /logout"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user:
        await message.answer("❌ <b>Вы не авторизованы</b>")
        return

    status = user.get("status")

    if status == UserStatus.ANONYMOUS:
        await delete_user(chat_id)
        await message.answer("🚪 <b>Процесс авторизации прерван</b>")
        return

    # AUTHORIZED пользователь
    await message.answer("🚪 <b>Вы вышли из системы</b>")
    await delete_user(chat_id)


@dp.message(Command("status"))
@rate_limit()
@safe_send_message
async def cmd_status(message: Message):
    """Обработчик /status"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user:
        user_status = "❌ <b>Не авторизован</b>"
        user_details = ""
    elif user.get("status") == UserStatus.ANONYMOUS:
        user_status = "🟡 <b>Ожидание авторизации</b>"
        user_details = f"\n🔧 Способ входа: код"
    else:
        user_status = "✅ <b>Авторизован</b>"
        email = user.get("email", "Неизвестно")
        user_details = f"\n📧 Email: {email}"

    redis_status = "🟢 онлайн" if redis_client.connected else "🔴 оффлайн"

    text = f"""
📊 <b>Статус системы</b>

━━━━━━━━━━━━━━━━━━
👤 <b>Ваш статус</b>
━━━━━━━━━━━━━━━━━━
{user_status}{user_details}

━━━━━━━━━━━━━━━━━━
🟢 <b>Сервисы</b>
━━━━━━━━━━━━━━━━━━
• Redis — {redis_status}
• Telegram Bot — 🟢 онлайн

━━━━━━━━━━━━━━━━━━
🔧 <b>Модули</b>
━━━━━━━━━━━━━━━━━━
• Auth Service — 🟡 заглушка
• Core Service — 🟡 заглушка
"""
    await message.answer(text)


@dp.message(Command("tests"))
@rate_limit()
@safe_send_message
async def cmd_tests(message: Message):
    """Список тестов - заглушка"""
    user = await get_user(message.chat.id)
    if not user or user.get("status") != UserStatus.AUTHORIZED:
        await message.answer("❌ <b>Требуется авторизация</b>\n\nИспользуйте /login для входа.")
        return

    text = """📚 <b>Доступные тесты</b>

1. <b>Python Basics</b> (10 вопросов) - активен
2. <b>Async IO</b> (8 вопросов) - активен
3. <b>Docker</b> (12 вопросов) - неактивен

Используйте /starttest <id> для начала теста."""

    await message.answer(text)


@dp.message(Command("courses"))
@rate_limit()
@safe_send_message
async def cmd_courses(message: Message):
    """Список курсов - заглушка"""
    user = await get_user(message.chat.id)
    if not user or user.get("status") != UserStatus.AUTHORIZED:
        await message.answer("❌ <b>Требуется авторизация</b>\n\nИспользуйте /login для входа.")
        return

    text = """🎓 <b>Доступные дисциплины</b>

1. <b>Программирование</b> - Основы программирования
2. <b>Базы данных</b> - SQL и NoSQL
3. <b>Сети</b> - Основы компьютерных сетей"""

    await message.answer(text)


@dp.message(Command("ping"))
@rate_limit()
@safe_send_message
async def cmd_ping(message: Message):
    await message.answer("🏓 <b>Pong!</b>\n\nБот работает корректно.")


@dp.message(Command("echo"))
@rate_limit()
@safe_send_message
async def cmd_echo(message: Message):
    text = message.text or ""
    if len(text) > 6:
        await message.answer(f"📢 <b>Эхо:</b> {text[6:]}")
    else:
        await message.answer("📢 <b>Напишите что-нибудь после /echo</b>")


@dp.message(Command("debug"))
@rate_limit()
@safe_send_message
async def cmd_debug(message: Message):
    chat_id = message.chat.id
    user = await get_user(chat_id)

    text = f"""
🐛 <b>Отладочная информация</b>

<b>Chat ID:</b> <code>{chat_id}</code>
<b>Redis подключен:</b> {"Да" if redis_client.connected else "Нет"}
<b>Пользователь в Redis:</b> {"Да" if user else "Нет"}

<b>Статус:</b> {user.get('status') if user else 'UNKNOWN'}
<b>Email:</b> {user.get('email') if user else 'Нет'}
"""
    await message.answer(text)


# =========================
# CALLBACK HANDLERS
# =========================
@dp.callback_query(F.data == "login")
async def callback_login(callback: CallbackQuery):
    await callback.answer()
    await cmd_login(callback.message)


@dp.callback_query(F.data.startswith("check_auth_"))
async def callback_check_auth(callback: CallbackQuery):
    login_token = callback.data[11:]
    result = await auth_service.check_login_token(login_token)

    if not result:
        await callback.answer("❌ Токен не найден или истек")
    elif result.get("status") == "pending":
        await callback.answer("⏳ Ожидание подтверждения входа")
    elif result.get("status") == "granted":
        user_data = result.get("user", {})
        access_token = result["access_token"]
        refresh_token = result["refresh_token"]

        await set_user_authorized(
            callback.from_user.id,
            access_token,
            refresh_token,
            user_data.get("id"),
            user_data.get("email")
        )

        await callback.answer("✅ Авторизация успешна!")
        await callback.message.edit_text(
            f"✅ <b>Авторизация завершена!</b>\n\nДобро пожаловать, {user_data.get('email')}",
            reply_markup=None
        )


@dp.callback_query(F.data == "cancel_auth")
async def callback_cancel_auth(callback: CallbackQuery):
    chat_id = callback.from_user.id
    await delete_user(chat_id)
    await callback.answer("❌ Авторизация отменена")
    await callback.message.edit_text("🚪 <b>Авторизация отменена</b>", reply_markup=None)


# =========================
# BACKGROUND TASK (упрощенная)
# =========================
async def check_anonymous_users_task():
    """Циклическая проверка anonymous пользователей"""
    while True:
        try:
            # Получаем всех пользователей
            keys = await redis_client.keys("user:*")
            for key in keys:
                data = await redis_client.get(key)
                if data:
                    user = json.loads(data)
                    if user.get("status") == UserStatus.ANONYMOUS:
                        login_token = user.get("login_token")
                        if login_token:
                            result = await auth_service.check_login_token(login_token)
                            if result and result.get("status") == "granted":
                                # Автоматическая авторизация
                                user_data = result.get("user", {})
                                access_token = result["access_token"]
                                refresh_token = result["refresh_token"]

                                # Извлекаем chat_id из ключа
                                try:
                                    chat_id = int(key.split(":")[1])
                                    await set_user_authorized(
                                        chat_id,
                                        access_token,
                                        refresh_token,
                                        user_data.get("id"),
                                        user_data.get("email")
                                    )

                                    # Отправляем уведомление
                                    await bot.send_message(
                                        chat_id,
                                        f"✅ <b>Авторизация успешно завершена!</b>\n\nДобро пожаловать, {user_data.get('email')}"
                                    )
                                except:
                                    pass
        except Exception as e:
            logger.error(f"Error in check_anonymous_users_task: {e}")

        await asyncio.sleep(10)  # Проверка каждые 10 секунд


# =========================
# MESSAGE HANDLER
# =========================
@dp.message()
@rate_limit()
@safe_send_message
async def handle_message(message: Message):
    """Обработчик всех сообщений"""
    text = message.text or ""
    if not text.startswith('/'):
        await message.answer("🤖 <b>Неизвестная команда</b>\n\nИспользуйте /help для просмотра доступных команд.")


# =========================
# MAIN
# =========================
async def main():
    logger.info("🤖 Telegram bot starting...")

    # Подключаем Redis
    await redis_client.connect()

    # Запускаем фоновую задачу
    background_task = asyncio.create_task(check_anonymous_users_task())

    logger.info("🚀 Bot is ready!")

    try:
        await dp.start_polling(bot, skip_updates=True)
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    finally:
        background_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())