import asyncio
import logging
import os
import json
import re
import secrets
import urllib.parse
from enum import Enum
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable, Awaitable
from functools import wraps

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest, TelegramRetryAfter

import redis.asyncio as redis
from dotenv import load_dotenv
import aiohttp
from aiohttp import ClientSession, ClientError, TCPConnector

# =========================
# ENV
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Эти URL будут пустыми, пока сервисы не созданы
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "")
CORE_SERVICE_URL = os.getenv("CORE_SERVICE_URL", "")
WEB_CLIENT_URL = os.getenv("WEB_CLIENT_URL", "https://example.com")  # Заменяем localhost на публичный URL

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("telegram-bot")

# =========================
# BOT - с увеличенными таймаутами
# =========================

bot = Bot(
    token=BOT_TOKEN,
    parse_mode=ParseMode.HTML,
)

dp = Dispatcher()


# =========================
# REDIS
# =========================

async def init_redis():
    """Инициализация Redis с повторными попытками"""
    max_retries = 5
    for i in range(max_retries):
        try:
            client = redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                retry_on_timeout=True,
                max_connections=10
            )
            await client.ping()
            logger.info(f"✅ Redis подключен (попытка {i + 1}/{max_retries})")
            return client
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Redis (попытка {i + 1}/{max_retries}): {e}")
            if i < max_retries - 1:
                await asyncio.sleep(2 ** i)  # Экспоненциальная задержка
            else:
                raise


try:
    redis_client = asyncio.run(init_redis())
except:
    logger.warning("⚠️ Redis недоступен, создаем заглушку")

    # Создаем заглушку Redis для работы без реального Redis
    class RedisStub:
        def __init__(self):
            self.data = {}

        async def get(self, key):
            return json.dumps(self.data.get(key)) if key in self.data else None

        async def setex(self, key, ttl, value):
            self.data[key] = json.loads(value)
            return True

        async def delete(self, key):
            if key in self.data:
                del self.data[key]
            return True

        async def keys(self, pattern):
            pattern_re = pattern.replace('*', '.*')
            return [k for k in self.data.keys() if re.match(pattern_re, k)]

        async def ping(self):
            return True

    redis_client = RedisStub()


# =========================
# USER STATUS (по ТЗ)
# =========================

class UserStatus(str, Enum):
    UNKNOWN = "unknown"
    ANONYMOUS = "anonymous"
    AUTHORIZED = "authorized"


# =========================
# RATE LIMIT FUNCTION (ИСПРАВЛЕНО: вынесена отдельно)
# =========================

async def check_rate_limit(chat_id: int, seconds: int = 2) -> bool:
    """Проверка лимита запросов для пользователя"""
    key = f"rate_limit:{chat_id}"
    try:
        last_time_str = await redis_client.get(key)

        if last_time_str:
            try:
                last_time = datetime.fromisoformat(last_time_str)
                if datetime.utcnow() - last_time < timedelta(seconds=seconds):
                    return False
            except:
                pass

        await redis_client.setex(key, seconds, datetime.utcnow().isoformat())
        return True
    except Exception as e:
        logger.error(f"Rate limit error: {e}")
        return True  # В случае ошибки пропускаем rate limit


# =========================
# REDIS HELPERS - с улучшенной обработкой ошибок
# =========================

async def get_user(chat_id: int) -> Optional[Dict]:
    """Получить пользователя из Redis"""
    try:
        data = await redis_client.get(f"user:{chat_id}")
        if data:
            if isinstance(data, str):
                return json.loads(data)
            return data
        return None
    except Exception as e:
        logger.error(f"Error getting user {chat_id}: {e}")
        return None


async def save_user(chat_id: int, data: Dict):
    """Сохранить пользователя в Redis"""
    try:
        data["updated_at"] = datetime.utcnow().isoformat()
        await redis_client.setex(
            f"user:{chat_id}",
            86400,  # 24 часа
            json.dumps(data)
        )
    except Exception as e:
        logger.error(f"Error saving user {chat_id}: {e}")
        # Локальное сохранение как fallback
        try:
            with open(f"user_{chat_id}.json", "w") as f:
                json.dump(data, f)
        except:
            pass


async def delete_user(chat_id: int):
    """Удалить пользователя из Redis"""
    try:
        await redis_client.delete(f"user:{chat_id}")
    except Exception as e:
        logger.error(f"Error deleting user {chat_id}: {e}")


async def set_user_anonymous(chat_id: int, login_token: str, provider: str = "code"):
    """Установить пользователя в статус ANONYMOUS"""
    await save_user(chat_id, {
        "status": UserStatus.ANONYMOUS,
        "login_token": login_token,
        "provider": provider,
        "created_at": datetime.utcnow().isoformat()
    })


async def set_user_authorized(chat_id: int, access_token: str, refresh_token: str, user_id: str, email: str):
    """Установить пользователя в статус AUTHORIZED"""
    await save_user(chat_id, {
        "status": UserStatus.AUTHORIZED,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user_id,
        "email": email,
        "authorized_at": datetime.utcnow().isoformat()
    })


async def get_user_status(chat_id: int) -> UserStatus:
    """Получить статус пользователя"""
    user = await get_user(chat_id)
    if not user:
        return UserStatus.UNKNOWN
    return UserStatus(user.get("status", UserStatus.UNKNOWN))


async def get_all_anonymous_users() -> List[Dict]:
    """Получить всех анонимных пользователей"""
    try:
        keys = await redis_client.keys("user:*")
        users = []
        for key in keys:
            data = await redis_client.get(key)
            if data:
                user = json.loads(data) if isinstance(data, str) else data
                if user.get("status") == UserStatus.ANONYMOUS:
                    try:
                        chat_id = int(key.split(":")[1])
                        user["chat_id"] = chat_id
                        users.append(user)
                    except:
                        pass
        return users
    except Exception as e:
        logger.error(f"Error getting anonymous users: {e}")
        return []


async def get_all_authorized_users() -> List[Dict]:
    """Получить всех авторизованных пользователей"""
    try:
        keys = await redis_client.keys("user:*")
        users = []
        for key in keys:
            data = await redis_client.get(key)
            if data:
                user = json.loads(data) if isinstance(data, str) else data
                if user.get("status") == UserStatus.AUTHORIZED:
                    try:
                        chat_id = int(key.split(":")[1])
                        user["chat_id"] = chat_id
                        users.append(user)
                    except:
                        pass
        return users
    except Exception as e:
        logger.error(f"Error getting authorized users: {e}")
        return []


# =========================
# HTTP CLIENT - с улучшенной обработкой ошибок
# =========================

class HTTPClient:
    """Клиент для HTTP запросов с обработкой ошибок"""

    def __init__(self):
        self.session: Optional[ClientSession] = None

    async def init_session(self):
        if not self.session or self.session.closed:
            connector = TCPConnector(limit=10, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=10)
            self.session = ClientSession(timeout=timeout, connector=connector)

    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def request(self, method: str, url: str, **kwargs) -> Optional[Dict]:
        """Выполнить HTTP запрос с обработкой ошибок"""
        try:
            await self.init_session()
            async with self.session.request(method, url, **kwargs) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status in [401, 403, 404, 418]:
                    return {
                        "error": True,
                        "status": response.status,
                        "message": await response.text()
                    }
                else:
                    logger.error(f"HTTP {method} {url} failed with status {response.status}")
                    return None
        except ClientError as e:
            logger.error(f"HTTP request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None


http_client = HTTPClient()


# =========================
# AUTH SERVICE STUB (улучшенная версия по ТЗ)
# =========================

class AuthServiceStub:
    """Улучшенная заглушка для сервиса авторизации с поддержкой провайдеров"""

    def __init__(self):
        self.login_tokens = {}
        self.refresh_tokens = {}
        self.codes = {}  # Для кодовой авторизации

    async def generate_login_url(self, login_token: str, provider: str = "code") -> str:
        """Генерация URL для авторизации с разными провайдерами"""
        # Инициализируем токен как ожидающий
        self.login_tokens[login_token] = {
            "status": "pending",
            "provider": provider,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(minutes=5)
        }

        if provider == "code":
            # Для кодовой авторизации генерируем цифровой код
            code = secrets.randbelow(900000) + 100000  # 6-значный код
            self.codes[code] = {
                "login_token": login_token,
                "expires_at": datetime.utcnow() + timedelta(minutes=5)
            }
            self.login_tokens[login_token]["code"] = code
            # Используем фиктивный URL для Telegram
            return "https://t.me/cfutgbot"
        elif provider == "github":
            # Используем фиктивный URL для Telegram
            return "https://github.com/login/oauth/authorize"
        elif provider == "yandex":
            # Используем фиктивный URL для Telegram
            return "https://oauth.yandex.ru/authorize"
        else:
            return "https://t.me/cfutgbot"

    async def check_login_token(self, login_token: str) -> Optional[Dict]:
        """Проверка статуса login_token"""
        if login_token not in self.login_tokens:
            return None

        token_data = self.login_tokens[login_token]

        # Проверяем истечение времени
        if datetime.utcnow() > token_data["expires_at"]:
            del self.login_tokens[login_token]
            return None

        status = token_data["status"]

        if status == "granted":
            # Пользователь подтвердил вход
            user_id = token_data.get("user_id", f"user_{secrets.token_hex(8)}")
            email = token_data.get("email", f"{user_id}@example.com")

            # Генерируем JWT токены
            access_token = f"access_{secrets.token_hex(16)}"
            refresh_token = f"refresh_{secrets.token_hex(16)}"

            # Сохраняем refresh токен
            self.refresh_tokens[refresh_token] = {
                "user_id": user_id,
                "email": email,
                "expires_at": datetime.utcnow() + timedelta(days=7)
            }

            # Удаляем использованный login token
            del self.login_tokens[login_token]

            return {
                "status": "granted",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": {
                    "id": user_id,
                    "email": email
                }
            }
        elif status == "denied":
            del self.login_tokens[login_token]
            return {"status": "denied"}
        else:
            return {"status": "pending"}

    async def verify_code(self, code: int, refresh_token: str) -> bool:
        """Проверка кода для кодовой авторизации"""
        if code not in self.codes:
            return False

        code_data = self.codes[code]
        if datetime.utcnow() > code_data["expires_at"]:
            del self.codes[code]
            return False

        # Проверяем refresh token (в реальности проверялась бы подпись)
        if not refresh_token.startswith("refresh_"):
            return False

        login_token = code_data["login_token"]
        if login_token in self.login_tokens:
            # Имитируем успешную авторизацию
            self.login_tokens[login_token]["status"] = "granted"
            # Извлекаем email из refresh token (в реальности из payload)
            user_id = f"user_{secrets.token_hex(8)}"
            self.login_tokens[login_token]["user_id"] = user_id
            self.login_tokens[login_token]["email"] = f"{user_id}@example.com"

            del self.codes[code]
            return True

        return False

    async def refresh_tokens(self, refresh_token: str) -> Optional[Dict]:
        """Обновление JWT токенов"""
        if refresh_token not in self.refresh_tokens:
            return None

        token_data = self.refresh_tokens[refresh_token]

        if datetime.utcnow() > token_data["expires_at"]:
            del self.refresh_tokens[refresh_token]
            return None

        user_id = token_data["user_id"]
        email = token_data["email"]

        # Генерируем новые токены
        new_access_token = f"access_{secrets.token_hex(16)}"
        new_refresh_token = f"refresh_{secrets.token_hex(16)}"

        # Обновляем refresh токен
        self.refresh_tokens[new_refresh_token] = {
            "user_id": user_id,
            "email": email,
            "expires_at": datetime.utcnow() + timedelta(days=7)
        }

        # Удаляем старый refresh token
        del self.refresh_tokens[refresh_token]

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token
        }

    async def logout_all(self, refresh_token: str) -> bool:
        """Выход со всех устройств"""
        if refresh_token in self.refresh_tokens:
            del self.refresh_tokens[refresh_token]
            return True
        return False

    # Методы для тестирования
    async def simulate_login_granted(self, login_token: str, user_id: str = None, email: str = None):
        """Имитировать успешную авторизацию"""
        if login_token in self.login_tokens:
            self.login_tokens[login_token]["status"] = "granted"
            self.login_tokens[login_token]["user_id"] = user_id or f"user_{secrets.token_hex(8)}"
            self.login_tokens[login_token]["email"] = email or f"{user_id}@example.com"

    async def simulate_login_denied(self, login_token: str):
        """Имитировать отклоненную авторизацию"""
        if login_token in self.login_tokens:
            self.login_tokens[login_token]["status"] = "denied"


auth_service = AuthServiceStub()


# =========================
# CORE SERVICE STUB
# =========================

class CoreServiceStub:
    """Заглушка для Core Service"""

    async def make_request(self, access_token: str, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """Выполнить запрос к Core Service"""
        if not access_token or not access_token.startswith("access_"):
            return {"error": True, "status": 401, "message": "Invalid token"}

        await asyncio.sleep(0.1)

        if endpoint == "/tests":
            return {
                "tests": [
                    {"id": 1, "name": "Python Basics", "active": True, "questions_count": 10},
                    {"id": 2, "name": "Async IO", "active": True, "questions_count": 8},
                    {"id": 3, "name": "Docker", "active": False, "questions_count": 12},
                ]
            }
        elif endpoint == "/courses":
            return {
                "courses": [
                    {"id": 1, "name": "Программирование", "description": "Основы программирования"},
                    {"id": 2, "name": "Базы данных", "description": "SQL и NoSQL"},
                ]
            }
        elif endpoint == "/notifications":
            return {"notifications": []}
        elif endpoint.startswith("/tests/"):
            try:
                test_id = endpoint.split("/")[2]
                return {
                    "test_id": int(test_id),
                    "name": f"Test {test_id}",
                    "questions": [
                        {"id": 1, "text": "Что такое Python?", "options": ["Язык", "Змея", "Оба"], "correct": 2},
                        {"id": 2, "text": "Что такое Docker?", "options": ["Контейнер", "Игра", "ОС"], "correct": 0},
                    ]
                }
            except:
                pass

        return {"error": True, "status": 404, "message": "Endpoint not found"}


core_service = CoreServiceStub()


# =========================
# DECORATORS
# =========================

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


def require_auth():
    """Декоратор для проверки авторизации"""

    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            chat_id = message.chat.id
            user = await get_user(chat_id)

            if not user:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔐 Авторизоваться", callback_data="login")]
                ])
                try:
                    await message.answer(
                        "❌ <b>Вы не авторизованы</b>\n\nПожалуйста, авторизуйтесь для доступа к этой команде.",
                        reply_markup=kb
                    )
                except Exception as e:
                    logger.error(f"Error sending auth message: {e}")
                return

            if user.get("status") == UserStatus.ANONYMOUS:
                try:
                    await message.answer(
                        "⏳ <b>Ожидание завершения авторизации</b>\n\nПроверьте статус или завершите вход в веб-клиенте.")
                except:
                    pass
                return

            return await handler(message, user, *args, **kwargs)

        return wrapper

    return decorator


def safe_send_message(func):
    """Декоратор для безопасной отправки сообщений с повторными попытками"""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        max_retries = 3
        for retry in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except TelegramRetryAfter as e:
                wait_time = e.retry_after
                logger.warning(f"Rate limit, waiting {wait_time} seconds")
                await asyncio.sleep(wait_time)
            except (TelegramNetworkError, TelegramBadRequest) as e:
                logger.error(f"Telegram error (attempt {retry + 1}/{max_retries}): {e}")
                if retry < max_retries - 1:
                    await asyncio.sleep(2 ** retry)
                else:
                    raise
            except Exception as e:
                logger.error(f"Unexpected error in {func.__name__}: {e}")
                raise

    return wrapper


# =========================
# COMMAND HANDLERS - с безопасной отправкой
# =========================

@dp.message(Command("start"))
@rate_limit()
@safe_send_message
async def cmd_start(message: Message):
    """Обработчик /start"""
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
        provider = user.get("provider", "code")

        # Получаем код из заглушки
        code = ""
        if login_token in auth_service.login_tokens:
            token_data = auth_service.login_tokens[login_token]
            if "code" in token_data:
                code = token_data["code"]

        text = f"""
🔐 <b>Ожидание авторизации</b>

Вы начали процесс входа через {provider}.
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
    """Обработчик /help"""
    help_text = """
🆘 <b>Справка по командам</b>

━━━━━━━━━━━━━━━━━━
🚀 <b>Основные команды</b>
━━━━━━━━━━━━━━━━━━
/start — начало работы  
/help — эта справка  
/status — статус системы  

━━━━━━━━━━━━━━━━━━
🔐 <b>Авторизация</b>
━━━━━━━━━━━━━━━━━━
/login — вход через код  
/logout — выход  
/logout all=true — выход со всех устройств  

━━━━━━━━━━━━━━━━━━
📚 <b>Дисциплины и тесты</b>
━━━━━━━━━━━━━━━━━━
/courses — список дисциплин  
/tests — список тестов  
/starttest <id> — начать тест  

━━━━━━━━━━━━━━━━━━
👤 <b>Профиль</b>
━━━━━━━━━━━━━━━━━━
/profile — информация о пользователе  
/myresults — мои результаты  

━━━━━━━━━━━━━━━━━━
⚙️ <b>Технические команды</b>
━━━━━━━━━━━━━━━━━━
/services — информация о сервисах  
/debug — отладочная информация  
"""
    await message.answer(help_text)


@dp.message(Command("login"))
@rate_limit()
@safe_send_message
async def cmd_login(message: Message):
    """Обработчик /login"""
    command_text = message.text or ""
    parts = command_text.split()

    # Всегда используем код для простоты
    provider = "code"

    chat_id = message.chat.id
    user = await get_user(chat_id)

    # Если уже авторизован
    if user and user.get("status") == UserStatus.AUTHORIZED:
        await message.answer(f"✅ <b>Вы уже авторизованы как {user.get('email')}</b>\n\nИспользуйте /logout для выхода.")
        return

    # Генерируем login_token
    login_token = secrets.token_urlsafe(32)

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
    command_text = message.text or ""
    logout_all = "all=true" in command_text.lower()

    if logout_all and user.get("refresh_token"):
        success = await auth_service.logout_all(user["refresh_token"])
        if success:
            await message.answer("✅ <b>Выход выполнен со всех устройств</b>")
        else:
            await message.answer("⚠️ <b>Не удалось выйти со всех устройств</b>")
    else:
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
        provider = user.get("provider", "code")
        provider_name = "код" if provider == "code" else provider
        user_details = f"\n🔧 Способ входа: {provider_name}"
    else:
        user_status = "✅ <b>Авторизован</b>"
        email = user.get("email", "Неизвестно")
        user_details = f"\n📧 Email: {email}"

    services_status = f"""
━━━━━━━━━━━━━━━━━━
🟢 <b>Сервисы</b>
━━━━━━━━━━━━━━━━━━
• Redis — {"🟢 онлайн" if not isinstance(redis_client, dict) else "🔴 оффлайн"}  
• Telegram Bot — 🟢 онлайн  

━━━━━━━━━━━━━━━━━━
🔧 <b>Модули</b>
━━━━━━━━━━━━━━━━━━
• Auth Service — 🟡 заглушка  
• Core Service — 🟡 заглушка  
• Web Client — 🟡 заглушка  
"""

    text = f"""
📊 <b>Статус системы</b>

━━━━━━━━━━━━━━━━━━
👤 <b>Ваш статус</b>
━━━━━━━━━━━━━━━━━━
{user_status}{user_details}
{services_status}
"""

    await message.answer(text)


@dp.message(Command("services"))
@rate_limit()
@safe_send_message
async def cmd_services(message: Message):
    """Обработчик /services"""
    text = """
🧩 <b>Архитектура системы</b>

━━━━━━━━━━━━━━━━━━
🤖 <b>Telegram Bot (этот модуль)</b>
━━━━━━━━━━━━━━━━━━
• Обработка команд пользователей  
• Управление состоянием через Redis  
• Отображение результатов тестов  
• Циклическая проверка статуса авторизации

━━━━━━━━━━━━━━━━━━
🔐 <b>Auth Service (заглушка)</b>
━━━━━━━━━━━━━━━━━━
• Авторизация через код  
• Выдача JWT токенов  
• Управление правами пользователей  

━━━━━━━━━━━━━━━━━━
⚙️ <b>Core Service (заглушка)</b>
━━━━━━━━━━━━━━━━━━
• Логика тестирования  
• Управление дисциплинами и тестами  
• Проверка разрешений  

━━━━━━━━━━━━━━━━━━
🌐 <b>Web Client (заглушка)</b>
━━━━━━━━━━━━━━━━━━
• Веб-интерфейс системы  
• Управление для преподавателей  
• Прохождение тестов  
"""
    await message.answer(text)


@dp.message(Command("debug"))
@rate_limit()
@safe_send_message
async def cmd_debug(message: Message):
    """Отладочная команда"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    redis_status = "🟢 онлайн" if not isinstance(redis_client, dict) else "🔴 оффлайн (заглушка)"

    text = f"""
🐛 <b>Отладочная информация</b>

<b>Chat ID:</b> <code>{chat_id}</code>
<b>Redis статус:</b> {redis_status}
<b>Пользователь в Redis:</b> {"Да" if user else "Нет"}

<b>Статус:</b> {user.get('status') if user else 'UNKNOWN'}
<b>User ID:</b> {user.get('user_id') if user else 'Нет'}
<b>Email:</b> {user.get('email') if user else 'Нет'}

<b>Логин токен:</b> {user.get('login_token')[:10] + '...' if user and user.get('login_token') else 'Нет'}
"""

    await message.answer(text)


# Простые команды без авторизации для тестирования
@dp.message(Command("ping"))
@rate_limit()
@safe_send_message
async def cmd_ping(message: Message):
    """Проверка работы бота"""
    await message.answer("🏓 <b>Pong!</b>\n\nБот работает корректно.")


@dp.message(Command("echo"))
@rate_limit()
@safe_send_message
async def cmd_echo(message: Message):
    """Эхо команда"""
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
    """Обработчик кнопки авторизации"""
    await callback.answer()
    await cmd_login(callback.message)


@dp.callback_query(F.data.startswith("check_auth_"))
async def callback_check_auth(callback: CallbackQuery):
    """Проверка статуса авторизации"""
    login_token = callback.data[11:]

    result = await auth_service.check_login_token(login_token)

    if not result:
        await callback.answer("❌ Токен не найден или истек")
    elif result.get("status") == "pending":
        await callback.answer("⏳ Ожидание подтверждения входа")
    elif result.get("status") == "denied":
        await callback.answer("❌ Авторизация отклонена")
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

        try:
            await callback.message.edit_text(
                f"✅ <b>Авторизация завершена!</b>\n\nДобро пожаловать, {user_data.get('email')}",
                reply_markup=None
            )
        except:
            await callback.message.answer(
                f"✅ <b>Авторизация завершена!</b>\n\nДобро пожаловать, {user_data.get('email')}")

    await callback.message.edit_reply_markup(reply_markup=None)


@dp.callback_query(F.data == "cancel_auth")
async def callback_cancel_auth(callback: CallbackQuery):
    """Отмена авторизации"""
    chat_id = callback.from_user.id
    await delete_user(chat_id)
    await callback.answer("❌ Авторизация отменена")
    await callback.message.edit_text("🚪 <b>Авторизация отменена</b>", reply_markup=None)


# =========================
# BACKGROUND TASKS
# =========================

async def check_anonymous_users_task():
    """Циклическая проверка anonymous пользователей"""
    logger.info("Starting anonymous users check task...")

    while True:
        try:
            anonymous_users = await get_all_anonymous_users()

            for user in anonymous_users:
                login_token = user.get("login_token")
                if not login_token:
                    continue

                result = await auth_service.check_login_token(login_token)

                if not result:
                    await delete_user(user["chat_id"])
                    continue

                if result.get("status") == "denied":
                    await delete_user(user["chat_id"])
                    try:
                        await bot.send_message(
                            user["chat_id"],
                            "❌ <b>Авторизация отклонена</b>\n\nВы отказались от входа в систему."
                        )
                    except:
                        pass
                    continue

                if result.get("status") == "granted":
                    user_data = result.get("user", {})
                    access_token = result["access_token"]
                    refresh_token = result["refresh_token"]

                    await set_user_authorized(
                        user["chat_id"],
                        access_token,
                        refresh_token,
                        user_data.get("id"),
                        user_data.get("email")
                    )

                    try:
                        await bot.send_message(
                            user["chat_id"],
                            f"✅ <b>Авторизация успешно завершена!</b>\n\nДобро пожаловать, {user_data.get('email')}"
                        )
                    except:
                        pass

        except Exception as e:
            logger.error(f"Error in check_anonymous_users_task: {e}")

        await asyncio.sleep(30)


async def check_notifications_task():
    """Циклическая проверка уведомлений"""
    logger.info("Starting notifications check task...")

    while True:
        try:
            authorized_users = await get_all_authorized_users()

            for user in authorized_users:
                access_token = user.get("access_token")
                if not access_token:
                    continue

                result = await core_service.make_request(
                    access_token,
                    "GET",
                    "/notifications"
                )

                if result and "notifications" in result:
                    notifications = result["notifications"]
                    for notification in notifications:
                        try:
                            await bot.send_message(
                                user["chat_id"],
                                f"📢 <b>{notification.get('title', 'Уведомление')}</b>\n\n{notification.get('message', '')}"
                            )
                        except:
                            pass

        except Exception as e:
            logger.error(f"Error in check_notifications_task: {e}")

        await asyncio.sleep(60)


# =========================
# MESSAGE HANDLER
# =========================

@dp.message()
@rate_limit()
@safe_send_message
async def handle_message(message: Message):
    """Обработчик всех сообщений"""
    chat_id = message.chat.id
    text = message.text or ""

    # Проверяем, есть ли активный тест
    try:
        context_data = await redis_client.get(f"test_context:{chat_id}")
        if context_data:
            await handle_test_answer(message,
                                     json.loads(context_data) if isinstance(context_data, str) else context_data)
            return
    except:
        pass

    # Если сообщение не команда, показываем справку
    if not text.startswith('/'):
        await message.answer("🤖 <b>Неизвестная команда</b>\n\nИспользуйте /help для просмотра доступных команд.")


async def handle_test_answer(message: Message, context: Dict):
    """Обработка ответа на вопрос теста"""
    chat_id = message.chat.id
    current_q = context.get("current_question", 0)
    questions = context.get("questions", [])

    if current_q >= len(questions):
        await redis_client.delete(f"test_context:{chat_id}")
        await message.answer("🎉 <b>Тест завершен!</b>\n\nРезультаты будут доступны в профиле.")
        return

    # Проверяем ответ
    try:
        answer = int(message.text.strip())
        if answer < 1 or answer > 3:
            raise ValueError
    except:
        await message.answer("❌ <b>Отправьте число от 1 до 3</b>")
        return

    if "answers" not in context:
        context["answers"] = {}
    context["answers"][current_q] = answer - 1
    context["current_question"] = current_q + 1

    if current_q + 1 < len(questions):
        await redis_client.setex(
            f"test_context:{chat_id}",
            3600,
            json.dumps(context)
        )

        question = questions[current_q + 1]
        text = f"""
<b>Вопрос {current_q + 2} из {len(questions)}:</b>
{question['text']}

1. {question['options'][0]}
2. {question['options'][1]}
3. {question['options'][2]}

<b>Отправьте номер правильного ответа (1-3).</b>
"""
        await message.answer(text)
    else:
        await redis_client.delete(f"test_context:{chat_id}")

        correct = 0
        for i, q in enumerate(questions):
            if context["answers"].get(i) == q.get("correct", -1):
                correct += 1

        score = int((correct / len(questions)) * 100) if questions else 0

        text = f"""
🎉 <b>Тест завершен!</b>

<b>Результат:</b> {score}%
<b>Правильных ответов:</b> {correct} из {len(questions)}

🏆 <b>Отличная работа!</b>
"""
        await message.answer(text)


async def handle_token_refresh(message: Message, user: Dict):
    """Обработка обновления токена"""
    refresh_token = user.get("refresh_token")

    if not refresh_token:
        await message.answer("❌ <b>Токен устарел</b>\n\nПожалуйста, выполните вход заново.")
        await delete_user(message.chat.id)
        return

    result = await auth_service.refresh_tokens(refresh_token)

    if not result:
        await message.answer("❌ <b>Сессия истекла</b>\n\nПожалуйста, выполните вход заново.")
        await delete_user(message.chat.id)
        return

    user["access_token"] = result["access_token"]
    user["refresh_token"] = result["refresh_token"]
    await save_user(message.chat.id, user)

    await message.answer("🔄 <b>Токен обновлен</b>\n\nПовторите запрос.")


# =========================
# TEST COMMANDS
# =========================

@dp.message(Command("simulate_login"))
@rate_limit()
@safe_send_message
async def cmd_simulate_login(message: Message):
    """Симуляция успешной авторизации"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user or user.get("status") != UserStatus.ANONYMOUS:
        await message.answer("❌ <b>Сначала выполните /login</b>")
        return

    login_token = user.get("login_token")
    if not login_token:
        await message.answer("❌ <b>Login token не найден</b>")
        return

    await auth_service.simulate_login_granted(login_token)

    await message.answer("✅ <b>Авторизация имитирована</b>\n\nНажмите 'Проверить статус' или подождите 30 секунд.")


@dp.message(Command("test_auth"))
@rate_limit()
@safe_send_message
async def cmd_test_auth(message: Message):
    """Тест авторизации"""
    chat_id = message.chat.id

    # Создаем тестового пользователя
    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "code")

    # Имитируем успешную авторизацию
    await auth_service.simulate_login_granted(login_token)

    await message.answer("✅ <b>Тестовый пользователь создан</b>\n\nЧерез 30 секунд вы будете авторизованы.")


# =========================
# MAIN - с улучшенной обработкой ошибок
# =========================

async def main():
    """Главная функция с обработкой переподключений"""
    logger.info("🤖 Telegram bot starting...")

    max_retries = 10
    retry_count = 0

    while retry_count < max_retries:
        try:
            background_tasks = [
                asyncio.create_task(check_anonymous_users_task()),
                asyncio.create_task(check_notifications_task()),
            ]

            logger.info("✅ Background tasks started")
            logger.info(f"📊 Redis URL: {REDIS_URL}")
            logger.info("🚀 Bot is ready!")

            await dp.start_polling(bot, skip_updates=True, allowed_updates=["message", "callback_query"])

            # Если polling завершился без ошибки, выходим
            break

        except TelegramNetworkError as e:
            retry_count += 1
            logger.error(f"Network error ({retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                wait_time = 5 * retry_count
                logger.info(f"Waiting {wait_time} seconds before retry...")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error("Max retries reached. Shutting down.")
                break
        except KeyboardInterrupt:
            logger.info("👋 Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            retry_count += 1
            if retry_count < max_retries:
                await asyncio.sleep(5)
                continue
            break
        finally:
            # Отменяем фоновые задачи
            for task in background_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error cancelling task: {e}")

            # Закрываем HTTP сессию
            await http_client.close_session()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error in main: {e}")