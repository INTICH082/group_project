import asyncio
import logging
import os
import json
import re
import secrets
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
from aiogram.exceptions import TelegramNetworkError

import redis.asyncio as redis
from dotenv import load_dotenv
import aiohttp
from aiohttp import ClientSession, ClientError

# =========================
# ENV
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Эти URL будут пустыми, пока сервисы не созданы
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "")
CORE_SERVICE_URL = os.getenv("CORE_SERVICE_URL", "")
WEB_CLIENT_URL = os.getenv("WEB_CLIENT_URL", "http://localhost:3000")

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

bot = Bot(
    token=BOT_TOKEN,
    parse_mode=ParseMode.HTML,
)

dp = Dispatcher()

# =========================
# REDIS
# =========================

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True,
)


# =========================
# USER STATUS (по ТЗ)
# =========================

class UserStatus(str, Enum):
    UNKNOWN = "unknown"
    ANONYMOUS = "anonymous"
    AUTHORIZED = "authorized"


# =========================
# REDIS HELPERS
# =========================

async def get_user(chat_id: int) -> Optional[Dict]:
    """Получить пользователя из Redis"""
    try:
        data = await redis_client.get(f"user:{chat_id}")
        return json.loads(data) if data else None
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
                user = json.loads(data)
                if user.get("status") == UserStatus.ANONYMOUS:
                    chat_id = int(key.split(":")[1])
                    user["chat_id"] = chat_id
                    users.append(user)
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
                user = json.loads(data)
                if user.get("status") == UserStatus.AUTHORIZED:
                    chat_id = int(key.split(":")[1])
                    user["chat_id"] = chat_id
                    users.append(user)
        return users
    except Exception as e:
        logger.error(f"Error getting authorized users: {e}")
        return []


# =========================
# HTTP CLIENT
# =========================

class HTTPClient:
    """Клиент для HTTP запросов с обработкой ошибок"""

    def __init__(self):
        self.session: Optional[ClientSession] = None

    async def init_session(self):
        if not self.session or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = ClientSession(timeout=timeout)

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
            return f"{WEB_CLIENT_URL}/login?token={login_token}&code={code}"
        elif provider == "github":
            # Имитация OAuth URL для GitHub
            return f"{WEB_CLIENT_URL}/oauth/github?state={login_token}"
        elif provider == "yandex":
            # Имитация OAuth URL для Яндекс
            return f"{WEB_CLIENT_URL}/oauth/yandex?state={login_token}"
        else:
            return f"{WEB_CLIENT_URL}/login?token={login_token}"

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

def rate_limit(seconds: int = 1):
    """Декоратор для ограничения частоты запросов"""

    async def check_rate_limit(chat_id: int) -> bool:
        key = f"rate_limit:{chat_id}"
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

    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            if not await check_rate_limit(message.chat.id):
                await message.answer("⏳ <b>Слишком много запросов. Подождите немного.</b>")
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
                    [InlineKeyboardButton(text="🔐 Авторизоваться", callback_data="cmd_login")]
                ])
                await message.answer(
                    "❌ <b>Вы не авторизованы</b>\n\nПожалуйста, авторизуйтесь для доступа к этой команде.",
                    reply_markup=kb
                )
                return

            if user.get("status") == UserStatus.ANONYMOUS:
                await message.answer(
                    "⏳ <b>Ожидание завершения авторизации</b>\n\nПроверьте статус или завершите вход в веб-клиенте.")
                return

            return await handler(message, user, *args, **kwargs)

        return wrapper

    return decorator


def timeout_handler(timeout_seconds=10):
    """Декоратор для обработки таймаутов"""

    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            try:
                return await asyncio.wait_for(
                    handler(message, *args, **kwargs),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                await message.answer("⏳ <b>Запрос выполняется дольше обычного...</b>")
                return

        return wrapper

    return decorator


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
        text = f"""
👋 <b>Добро пожаловать, {message.from_user.first_name or 'пользователь'}!</b>

🤖 <b>Telegram-клиент системы тестирования</b>

Для начала работы необходимо авторизоваться.

Используйте команду /login для входа в систему.
"""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔐 Авторизоваться", callback_data="cmd_login")]
        ])
    elif user.get("status") == UserStatus.ANONYMOUS:
        login_token = user.get("login_token", "")
        provider = user.get("provider", "code")

        if provider == "code" and "code" in auth_service.login_tokens.get(login_token, {}):
            code = auth_service.login_tokens[login_token]["code"]
            code_text = f"\nКод для ввода: <code>{code}</code>"
        else:
            code_text = ""

        text = f"""
🔐 <b>Ожидание авторизации</b>

Вы начали процесс входа через {provider}.
Для завершения авторизации:

1. Перейдите в веб-клиент
2. Следуйте инструкциям{code_text}

Или нажмите "Проверить статус".
"""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
            [InlineKeyboardButton(text="🌐 Открыть веб-клиент", url=WEB_CLIENT_URL)],
            [InlineKeyboardButton(text="🔄 Начать заново", callback_data="cmd_login")]
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
/login — вход через код (по умолчанию)  
/login github — вход через GitHub  
/login yandex — вход через Яндекс  
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
async def cmd_login(message: Message):
    """Обработчик /login с поддержкой провайдеров"""
    command_text = message.text or ""
    parts = command_text.split()

    # Определяем провайдера
    provider = "code"  # по умолчанию код
    if len(parts) > 1:
        if parts[1] in ["github", "yandex", "code"]:
            provider = parts[1]

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

    # Создаем соответствующую клавиатуру
    if provider == "code":
        code = auth_service.login_tokens[login_token]["code"]
        text = f"""
🔐 <b>Авторизация через код</b>

Для входа в систему введите код в веб-клиенте:

<code>{code}</code>

Или перейдите по ссылке ниже.

⏳ <b>Код действителен 5 минут</b>
"""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Открыть веб-клиент", url=auth_url)],
            [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")]
        ])
    else:
        provider_name = "GitHub" if provider == "github" else "Яндекс"
        text = f"""
🔐 <b>Авторизация через {provider_name}</b>

Нажмите кнопку ниже для авторизации через {provider_name}.

⏳ <b>Ссылка действительна 5 минут</b>
"""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🔗 Войти через {provider_name}", url=auth_url)],
            [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")]
        ])

    await message.answer(text, reply_markup=kb)


@dp.message(Command("login_github"))
@rate_limit()
async def cmd_login_github(message: Message):
    """Авторизация через GitHub"""
    message.text = "/login github"
    await cmd_login(message)


@dp.message(Command("login_yandex"))
@rate_limit()
async def cmd_login_yandex(message: Message):
    """Авторизация через Яндекс"""
    message.text = "/login yandex"
    await cmd_login(message)


@dp.message(Command("logout"))
@rate_limit()
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

    services_status = """
━━━━━━━━━━━━━━━━━━
🟢 <b>Сервисы</b>
━━━━━━━━━━━━━━━━━━
• Redis — онлайн  
• Telegram Bot — онлайн  

━━━━━━━━━━━━━━━━━━
🔧 <b>Модули (в разработке)</b>
━━━━━━━━━━━━━━━━━━
• Auth Service — 🟡 заглушка  
• Core Service — 🟡 заглушка  
• Web Client — 🔴 не доступен  
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
• Авторизация через GitHub/Yandex/код  
• Выдача JWT токенов  
• Управление правами пользователей  

━━━━━━━━━━━━━━━━━━
⚙️ <b>Core Service (заглушка)</b>
━━━━━━━━━━━━━━━━━━
• Логика тестирования  
• Управление дисциплинами и тестами  
• Проверка разрешений  

━━━━━━━━━━━━━━━━━━
🌐 <b>Web Client (в разработке)</b>
━━━━━━━━━━━━━━━━━━
• Веб-интерфейс системы  
• Управление для преподавателей  
• Прохождение тестов  
"""
    await message.answer(text)


@dp.message(Command("tests"))
@rate_limit()
@timeout_handler(5)
@require_auth()
async def cmd_tests(message: Message, user: Dict):
    """Обработчик /tests"""
    result = await core_service.make_request(
        user.get("access_token"),
        "GET",
        "/tests"
    )

    if result and "error" in result:
        if result.get("status") == 401:
            await handle_token_refresh(message, user)
            return
        elif result.get("status") == 403:
            await message.answer("❌ <b>Недостаточно прав</b>\n\nУ вас нет доступа к списку тестов.")
            return
        else:
            await message.answer("⚠️ <b>Ошибка при получении тестов</b>")
            return

    if not result or "tests" not in result:
        await message.answer("📭 <b>Тесты не найдены</b>")
        return

    tests = result["tests"]

    keyboard = []
    for test in tests:
        status = "🟢" if test.get("active") else "🔴"
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {test['name']} ({test.get('questions_count', 0)} вопросов)",
                callback_data=f"start_test_{test['id']}"
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    text = """
🧪 <b>Доступные тесты</b>

Выберите тест для начала:
"""

    await message.answer(text, reply_markup=kb)


@dp.message(Command("courses"))
@rate_limit()
@timeout_handler(5)
@require_auth()
async def cmd_courses(message: Message, user: Dict):
    """Обработчик /courses"""
    result = await core_service.make_request(
        user.get("access_token"),
        "GET",
        "/courses"
    )

    if result and "error" in result:
        if result.get("status") == 401:
            await handle_token_refresh(message, user)
            return
        elif result.get("status") == 403:
            await message.answer("❌ <b>Недостаточно прав</b>\n\nУ вас нет доступа к списку дисциплин.")
            return
        else:
            await message.answer("⚠️ <b>Ошибка при получении дисциплин</b>")
            return

    if not result or "courses" not in result:
        await message.answer("📭 <b>Дисциплины не найдены</b>")
        return

    courses = result["courses"]

    text = """
📚 <b>Доступные дисциплины</b>

"""

    for course in courses:
        text += f"• <b>{course['name']}</b> (ID: {course['id']})\n"
        text += f"  {course['description']}\n\n"

    await message.answer(text)


@dp.message(Command("starttest"))
@rate_limit()
@require_auth()
async def cmd_starttest(message: Message, user: Dict):
    """Обработчик /starttest <id>"""
    command_text = message.text or ""
    parts = command_text.split()

    if len(parts) < 2:
        await message.answer("❌ <b>Укажите ID теста</b>\n\nИспользование: <code>/starttest &lt;ID_теста&gt;</code>")
        return

    try:
        test_id = int(parts[1])
    except ValueError:
        await message.answer("❌ <b>Неверный формат ID</b>\n\nID должен быть числом.")
        return

    result = await core_service.make_request(
        user.get("access_token"),
        "POST",
        f"/tests/{test_id}/start"
    )

    if result and "error" in result:
        if result.get("status") == 401:
            await handle_token_refresh(message, user)
            return
        elif result.get("status") == 403:
            await message.answer("❌ <b>Недостаточно прав</b>\n\nУ вас нет доступа к этому тесту.")
            return
        elif result.get("status") == 418:
            await message.answer("🚫 <b>Пользователь заблокирован</b>\n\nДоступ к системе ограничен.")
            return
        else:
            await message.answer("⚠️ <b>Ошибка при запуске теста</b>")
            return

    if not result:
        await message.answer("⚠️ <b>Не удалось начать тест</b>")
        return

    await redis_client.setex(
        f"test_context:{user.get('chat_id')}",
        3600,
        json.dumps({
            "attempt_id": result.get("attempt_id", "test_1"),
            "test_id": test_id,
            "questions": result.get("questions", []),
            "current_question": 0,
            "started_at": datetime.utcnow().isoformat()
        })
    )

    questions = result.get("questions", [])
    if questions:
        question = questions[0]
        text = f"""
🎯 <b>Тест начат!</b>

<b>Вопрос 1 из {len(questions)}:</b>
{question['text']}

1. {question['options'][0]}
2. {question['options'][1]}
3. {question['options'][2]}

<b>Отправьте номер правильного ответа (1-3).</b>
"""
        await message.answer(text)


@dp.message(Command("profile"))
@rate_limit()
@require_auth()
async def cmd_profile(message: Message, user: Dict):
    """Обработчик /profile"""
    user_id = user.get("user_id", "Неизвестно")
    email = user.get("email", "Неизвестно")

    text = f"""
👤 <b>Профиль пользователя</b>

<b>ID:</b> <code>{user_id}</code>
<b>Email:</b> {email}
<b>Авторизован:</b> {user.get('authorized_at', 'Неизвестно')}

━━━━━━━━━━━━━━━━━━
📊 <b>Статистика</b>
━━━━━━━━━━━━━━━━━━
• Пройдено тестов: 0
• Средний балл: 0%
• Активных попыток: 0

<b>Данные загружаются из Core Service...</b>
"""

    await message.answer(text)


@dp.message(Command("debug"))
@rate_limit()
async def cmd_debug(message: Message):
    """Отладочная команда"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    text = f"""
🐛 <b>Отладочная информация</b>

<b>Chat ID:</b> <code>{chat_id}</code>
<b>Пользователь в Redis:</b> {"Да" if user else "Нет"}

<b>Статус:</b> {user.get('status') if user else 'UNKNOWN'}
<b>User ID:</b> {user.get('user_id') if user else 'Нет'}
"""

    await message.answer(text)


# =========================
# CALLBACK HANDLERS
# =========================

@dp.callback_query(F.data.startswith("cmd_"))
async def callback_command(callback: CallbackQuery):
    """Обработчик callback команд"""
    command = callback.data[4:]

    if command == "login":
        await cmd_login(callback.message)
    elif command == "tests":
        await cmd_tests(callback.message)

    await callback.answer()


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

        await callback.message.edit_text(
            f"✅ <b>Авторизация завершена!</b>\n\nДобро пожаловать, {user_data.get('email')}",
            reply_markup=None
        )

    await callback.message.edit_reply_markup(reply_markup=None)


@dp.callback_query(F.data.startswith("show_token_"))
async def callback_show_token(callback: CallbackQuery):
    """Показать токен для ручного ввода"""
    login_token = callback.data[11:]

    await callback.answer(
        f"Код для ввода в веб-клиенте:\n\n{login_token}",
        show_alert=True
    )


@dp.callback_query(F.data.startswith("start_test_"))
async def callback_start_test(callback: CallbackQuery):
    """Начать тест через inline-кнопку"""
    try:
        test_id = int(callback.data[11:])

        user = await get_user(callback.from_user.id)
        if not user or user.get("status") != UserStatus.AUTHORIZED:
            await callback.answer("❌ Требуется авторизация")
            return

        result = await core_service.make_request(
            user.get("access_token"),
            "POST",
            f"/tests/{test_id}/start"
        )

        if result and "error" in result:
            await callback.answer(f"Ошибка: {result.get('message', 'Неизвестная ошибка')}")
            return

        if not result:
            await callback.answer("❌ Не удалось начать тест")
            return

        await redis_client.setex(
            f"test_context:{callback.from_user.id}",
            3600,
            json.dumps({
                "attempt_id": result.get("attempt_id", "test_1"),
                "test_id": test_id,
                "questions": result.get("questions", []),
                "current_question": 0,
                "started_at": datetime.utcnow().isoformat()
            })
        )

        questions = result.get("questions", [])
        if questions:
            question = questions[0]
            text = f"""
🎯 <b>Тест начат!</b>

<b>Вопрос 1 из {len(questions)}:</b>
{question['text']}

1. {question['options'][0]}
2. {question['options'][1]}
3. {question['options'][2]}

<b>Отправьте номер правильного ответа (1-3).</b>
"""
            await callback.message.edit_text(text)

        await callback.answer()

    except Exception as e:
        logger.error(f"Error starting test: {e}")
        await callback.answer("❌ Ошибка при запуске теста")


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
async def handle_message(message: Message):
    """Обработчик всех сообщений"""
    chat_id = message.chat.id
    text = message.text or ""

    context_data = await redis_client.get(f"test_context:{chat_id}")
    if context_data:
        await handle_test_answer(message, json.loads(context_data))
        return

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


@dp.message(Command("verify_code"))
@rate_limit()
async def cmd_verify_code(message: Message):
    """Проверка кода для отладки"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user or user.get("status") != UserStatus.ANONYMOUS:
        await message.answer("❌ <b>Сначала выполните /login</b>")
        return

    login_token = user.get("login_token")
    if not login_token:
        await message.answer("❌ <b>Login token не найден</b>")
        return

    if login_token in auth_service.login_tokens:
        code = auth_service.login_tokens[login_token].get("code")
        if code:
            success = await auth_service.verify_code(code, "refresh_test")
            if success:
                await message.answer(f"✅ <b>Код {code} проверен успешно!</b>\n\nНажмите 'Проверить статус'.")
            else:
                await message.answer("❌ <b>Не удалось проверить код</b>")
        else:
            await message.answer("❌ <b>Код не найден</b>")
    else:
        await message.answer("❌ <b>Токен не найден</b>")


# =========================
# MAIN
# =========================

async def main():
    """Главная функция с обработкой переподключений"""
    logger.info("🤖 Telegram bot starting...")

    max_retries = 5
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

            await dp.start_polling(bot, skip_updates=True)

        except TelegramNetworkError as e:
            retry_count += 1
            logger.error(f"Network error ({retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                await asyncio.sleep(5 * retry_count)  # Экспоненциальная задержка
                continue
            else:
                logger.error("Max retries reached. Shutting down.")
                break
        except KeyboardInterrupt:
            logger.info("👋 Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            break
        finally:
            # Отменяем фоновые задачи
            for task in background_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Закрываем HTTP сессию
            await http_client.close_session()


if __name__ == "__main__":
    asyncio.run(main())