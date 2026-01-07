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
# MARKDOWN V2 SAFE
# =========================

def md(text: str) -> str:
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)


# =========================
# BOT
# =========================

bot = Bot(
    token=BOT_TOKEN,
    parse_mode=ParseMode.MARKDOWN_V2,
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
    UNKNOWN = "unknown"  # Неизвестный
    ANONYMOUS = "anonymous"  # Анонимный (имеет login_token)
    AUTHORIZED = "authorized"  # Авторизованный (имеет JWT токены)


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


async def set_user_anonymous(chat_id: int, login_token: str):
    """Установить пользователя в статус ANONYMOUS"""
    await save_user(chat_id, {
        "status": UserStatus.ANONYMOUS,
        "login_token": login_token,
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
            self.session = ClientSession()

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
# AUTH SERVICE STUB (минимальный, по ТЗ)
# =========================

class AuthServiceStub:
    """Заглушка для сервиса авторизации, реализующая только логику по ТЗ"""

    def __init__(self):
        # Хранилище login токенов: token -> {"status": "pending"/"granted"/"denied", "user_id": ...}
        self.login_tokens = {}
        # Хранилище refresh токенов: token -> {"user_id": ..., "expires": ...}
        self.refresh_tokens = {}

    async def generate_login_url(self, login_token: str, provider: str = "github") -> str:
        """Генерация URL для авторизации (по ТЗ)"""
        # Инициализируем токен как ожидающий
        self.login_tokens[login_token] = {
            "status": "pending",
            "provider": provider,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(minutes=5)
        }

        # Возвращаем URL для веб-клиента (в реальности был бы OAuth URL)
        return f"{WEB_CLIENT_URL}/login?token={login_token}"

    async def check_login_token(self, login_token: str) -> Optional[Dict]:
        """Проверка статуса login_token (по ТЗ)"""
        if login_token not in self.login_tokens:
            return None

        token_data = self.login_tokens[login_token]

        # Проверяем истечение времени
        if datetime.utcnow() > token_data["expires_at"]:
            del self.login_tokens[login_token]
            return None

        status = token_data["status"]

        if status == "granted":
            # Пользователь подтвердил вход, генерируем JWT токены
            user_id = token_data.get("user_id", f"user_{secrets.token_hex(8)}")
            email = token_data.get("email", f"{user_id}@example.com")

            # Генерируем токены (заглушки)
            access_token = f"access_{secrets.token_hex(16)}"
            refresh_token = f"refresh_{secrets.token_hex(16)}"

            # Сохраняем refresh токен
            self.refresh_tokens[refresh_token] = {
                "user_id": user_id,
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

    async def refresh_tokens(self, refresh_token: str) -> Optional[Dict]:
        """Обновление JWT токенов (по ТЗ)"""
        if refresh_token not in self.refresh_tokens:
            return None

        token_data = self.refresh_tokens[refresh_token]

        if datetime.utcnow() > token_data["expires_at"]:
            del self.refresh_tokens[refresh_token]
            return None

        user_id = token_data["user_id"]

        # Генерируем новые токены
        new_access_token = f"access_{secrets.token_hex(16)}"
        new_refresh_token = f"refresh_{secrets.token_hex(16)}"

        # Обновляем refresh токен
        self.refresh_tokens[new_refresh_token] = {
            "user_id": user_id,
            "expires_at": datetime.utcnow() + timedelta(days=7)
        }

        # Удаляем старый refresh token
        del self.refresh_tokens[refresh_token]

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token
        }

    async def logout_all(self, refresh_token: str) -> bool:
        """Выход со всех устройств (по ТЗ)"""
        if refresh_token in self.refresh_tokens:
            del self.refresh_tokens[refresh_token]
            return True
        return False

    # Методы для тестирования
    async def simulate_login_granted(self, login_token: str, user_id: str = None, email: str = None):
        """Имитировать успешную авторизацию (для тестов)"""
        if login_token in self.login_tokens:
            self.login_tokens[login_token]["status"] = "granted"
            self.login_tokens[login_token]["user_id"] = user_id or f"user_{secrets.token_hex(8)}"
            self.login_tokens[login_token]["email"] = email or f"{user_id}@example.com"

    async def simulate_login_denied(self, login_token: str):
        """Имитировать отклоненную авторизацию (для тестов)"""
        if login_token in self.login_tokens:
            self.login_tokens[login_token]["status"] = "denied"


auth_service = AuthServiceStub()


# =========================
# CORE SERVICE STUB (минимальный, по ТЗ)
# =========================

class CoreServiceStub:
    """Заглушка для Core Service, реализующая логику по ТЗ"""

    async def make_request(self, access_token: str, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """Выполнить запрос к Core Service (по ТЗ)"""
        # В реальности здесь был бы HTTP запрос к Core Service
        # С заглушкой возвращаем тестовые данные или ошибки

        # Проверяем access token (заглушка)
        if not access_token or not access_token.startswith("access_"):
            return {"error": True, "status": 401, "message": "Invalid token"}

        # Имитируем задержку сети
        await asyncio.sleep(0.1)

        # Обрабатываем различные эндпоинты
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

        elif endpoint.startswith("/tests/"):
            test_id = endpoint.split("/")[2]
            return {
                "test_id": int(test_id),
                "name": f"Test {test_id}",
                "questions": [
                    {"id": 1, "text": "Что такое Python?", "options": ["Язык", "Змея", "Оба"], "correct": 2},
                    {"id": 2, "text": "Что такое Docker?", "options": ["Контейнер", "Игра", "ОС"], "correct": 0},
                ]
            }

        elif endpoint == "/notifications":
            # Возвращаем пустые уведомления (в реальности были бы реальные)
            return {"notifications": []}

        else:
            # Для неизвестных эндпоинтов возвращаем 404
            return {"error": True, "status": 404, "message": "Endpoint not found"}


core_service = CoreServiceStub()


# =========================
# DECORATORS
# =========================

def rate_limit():
    """Декоратор для ограничения частоты запросов (1 запрос в секунду)"""

    async def check_rate_limit(chat_id: int) -> bool:
        key = f"rate_limit:{chat_id}"
        last_time_str = await redis_client.get(key)

        if last_time_str:
            try:
                last_time = datetime.fromisoformat(last_time_str)
                if datetime.utcnow() - last_time < timedelta(seconds=1):
                    return False
            except:
                pass

        await redis_client.setex(key, 1, datetime.utcnow().isoformat())
        return True

    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            if not await check_rate_limit(message.chat.id):
                await message.answer(md("⏳ *Слишком много запросов\\. Подождите 1 секунду\\.*"))
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
                # UNKNOWN пользователь
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔐 Авторизоваться", callback_data="cmd_login")]
                ])
                await message.answer(
                    md("❌ *Вы не авторизованы*\n\nИспользуйте /login для входа в систему\\."),
                    reply_markup=kb
                )
                return

            if user.get("status") == UserStatus.ANONYMOUS:
                # ANONYMOUS пользователь
                await message.answer(
                    md("⏳ *Ожидание завершения авторизации*\n\nПроверьте статус или завершите вход в веб\\-клиенте\\."))
                return

            # AUTHORIZED пользователь
            return await handler(message, user, *args, **kwargs)

        return wrapper

    return decorator


# =========================
# COMMAND HANDLERS (по ТЗ)
# =========================

@dp.message(Command("start"))
@rate_limit()
async def cmd_start(message: Message):
    """Обработчик /start (Сценарий 1: Неизвестный пользователь)"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user:
        # Пользователь UNKNOWN
        text = f"""
👋 *Добро пожаловать, {message.from_user.first_name or 'пользователь'}*\\!

🤖 *Telegram\\-клиент системы тестирования*

Для начала работы необходимо авторизоваться\\.

Используйте команду /login для входа в систему\\.
"""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔐 Авторизоваться", callback_data="cmd_login")]
        ])
    elif user.get("status") == UserStatus.ANONYMOUS:
        # Пользователь ANONYMOUS
        login_token = user.get("login_token", "")
        text = f"""
🔐 *Ожидание авторизации*

Вы начали процесс входа\\.
Для завершения авторизации:

1\\. Перейдите в веб\\-клиент
2\\. Введите код: `{login_token}`
3\\. Подтвердите вход

Или нажмите "Проверить статус"\\.
"""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
            [InlineKeyboardButton(text="🌐 Открыть веб-клиент", url=WEB_CLIENT_URL)],
            [InlineKeyboardButton(text="🔄 Начать заново", callback_data="cmd_login")]
        ])
    else:
        # Пользователь AUTHORIZED
        user_email = user.get("email", "пользователь")
        text = f"""
✅ *Вы авторизованы как {user_email}*

Доступные команды:
/tests — список тестов
/courses — список дисциплин
/profile — ваш профиль
/logout — выход из системы

Используйте /help для полного списка команд\\.
"""
        kb = None

    await message.answer(md(text), reply_markup=kb)


@dp.message(Command("help"))
@rate_limit()
async def cmd_help(message: Message):
    """Обработчик /help"""
    help_text = """
🆘 *Справка по командам*

━━━━━━━━━━━━━━━━━━
🚀 *Основные команды*
━━━━━━━━━━━━━━━━━━
/start — начало работы  
/help — эта справка  
/status — статус системы  

━━━━━━━━━━━━━━━━━━
🔐 *Авторизация*
━━━━━━━━━━━━━━━━━━
/login — вход в систему  
/logout — выход  
/logout all=true — выход со всех устройств  

━━━━━━━━━━━━━━━━━━
📚 *Дисциплины и тесты*
━━━━━━━━━━━━━━━━━━
/courses — список дисциплин  
/tests — список тестов  
/starttest <id> — начать тест  

━━━━━━━━━━━━━━━━━━
👤 *Профиль*
━━━━━━━━━━━━━━━━━━
/profile — информация о пользователе  
/myresults — мои результаты  

━━━━━━━━━━━━━━━━━━
⚙️ *Технические команды*
━━━━━━━━━━━━━━━━━━
/services — информация о сервисах  
/debug — отладочная информация  
"""
    await message.answer(md(help_text))


@dp.message(Command("login"))
@rate_limit()
async def cmd_login(message: Message):
    """Обработчик /login (Сценарий 1 и 2 по ТЗ)"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    # Если уже авторизован
    if user and user.get("status") == UserStatus.AUTHORIZED:
        await message.answer(md("✅ *Вы уже авторизованы*\n\nИспользуйте /logout для выхода\\."))
        return

    # Генерируем новый login_token
    login_token = secrets.token_urlsafe(32)

    # Устанавливаем пользователя как ANONYMOUS
    await set_user_anonymous(chat_id, login_token)

    # Получаем URL для авторизации
    auth_url = await auth_service.generate_login_url(login_token)

    # Создаем клавиатуру
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Войти через веб-клиент", url=auth_url)],
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
        [InlineKeyboardButton(text="📋 Показать код для ввода", callback_data=f"show_token_{login_token}")]
    ])

    text = f"""
🔐 *Авторизация*

Для входа в систему:

1\\. *Вариант 1:* Перейдите по ссылке выше
2\\. *Вариант 2:* В веб\\-клиенте введите код:

`{login_token}`

⏳ *Код действителен 5 минут*

После подтверждения входа нажмите "Проверить статус"\\.
"""

    await message.answer(md(text), reply_markup=kb)


@dp.message(Command("logout"))
@rate_limit()
async def cmd_logout(message: Message):
    """Обработчик /logout (Сценарий 3 по ТЗ)"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user:
        await message.answer(md("❌ *Вы не авторизованы*"))
        return

    status = user.get("status")

    if status == UserStatus.ANONYMOUS:
        await delete_user(chat_id)
        await message.answer(md("🚪 *Процесс авторизации прерван*"))
        return

    # AUTHORIZED пользователь
    command_text = message.text or ""
    logout_all = "all=true" in command_text.lower()

    if logout_all and user.get("refresh_token"):
        # Выход со всех устройств
        success = await auth_service.logout_all(user["refresh_token"])
        if success:
            await message.answer(md("✅ *Выход выполнен со всех устройств*"))
        else:
            await message.answer(md("⚠️ *Не удалось выйти со всех устройств*"))
    else:
        await message.answer(md("🚪 *Вы вышли из системы*"))

    # Удаляем пользователя из Redis
    await delete_user(chat_id)


@dp.message(Command("status"))
@rate_limit()
async def cmd_status(message: Message):
    """Обработчик /status"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    # Статус пользователя
    if not user:
        user_status = "❌ *Не авторизован*"
        user_details = ""
    elif user.get("status") == UserStatus.ANONYMOUS:
        user_status = "🟡 *Ожидание авторизации*"
        token = user.get("login_token", "")[:10] + "..."
        user_details = f"\n🔢 Токен: `{token}`"
    else:
        user_status = "✅ *Авторизован*"
        email = user.get("email", "Неизвестно")
        user_details = f"\n📧 Email: {email}"

    # Статус сервисов
    services_status = """
━━━━━━━━━━━━━━━━━━
🟢 *Сервисы*
━━━━━━━━━━━━━━━━━━
• Redis — онлайн  
• Telegram Bot — онлайн  

━━━━━━━━━━━━━━━━━━
🔧 *Модули* \\(в разработке\\)
━━━━━━━━━━━━━━━━━━
• Auth Service — ❌ не доступен  
• Core Service — ❌ не доступен  
• Web Client — ❌ не доступен  
"""

    text = f"""
📊 *Статус системы*

━━━━━━━━━━━━━━━━━━
👤 *Ваш статус*
━━━━━━━━━━━━━━━━━━
{user_status}{user_details}
{services_status}
"""

    await message.answer(md(text))


@dp.message(Command("services"))
@rate_limit()
async def cmd_services(message: Message):
    """Обработчик /services"""
    text = """
🧩 *Архитектура системы*

━━━━━━━━━━━━━━━━━━
🤖 *Telegram Bot* \\(этот модуль\\)
━━━━━━━━━━━━━━━━━━
• Обработка команд пользователей  
• Управление состоянием через Redis  
• Отображение результатов тестов  

━━━━━━━━━━━━━━━━━━
🔐 *Auth Service* \\(в разработке\\)
━━━━━━━━━━━━━━━━━━
• Авторизация через GitHub/Yandex  
• Выдача JWT токенов  
• Управление правами пользователей  

━━━━━━━━━━━━━━━━━━
⚙️ *Core Service* \\(в разработке\\)
━━━━━━━━━━━━━━━━━━
• Логика тестирования  
• Управление дисциплинами и тестами  
• Проверка разрешений  

━━━━━━━━━━━━━━━━━━
🌐 *Web Client* \\(в разработке\\)
━━━━━━━━━━━━━━━━━━
• Веб-интерфейс системы  
• Управление для преподавателей  
• Прохождение тестов  
"""
    await message.answer(md(text))


@dp.message(Command("tests"))
@rate_limit()
@require_auth()
async def cmd_tests(message: Message, user: Dict):
    """Обработчик /tests (только для авторизованных)"""
    # Получаем тесты из Core Service
    result = await core_service.make_request(
        user.get("access_token"),
        "GET",
        "/tests"
    )

    if result and "error" in result:
        if result.get("status") == 401:
            # Токен устарел, пытаемся обновить
            await handle_token_refresh(message, user)
            return
        elif result.get("status") == 403:
            await message.answer(md("❌ *Недостаточно прав*\n\nУ вас нет доступа к списку тестов\\."))
            return
        else:
            await message.answer(md("⚠️ *Ошибка при получении тестов*"))
            return

    if not result or "tests" not in result:
        await message.answer(md("📭 *Тесты не найдены*"))
        return

    tests = result["tests"]

    # Создаем клавиатуру с тестами
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
🧪 *Доступные тесты*

Выберите тест для начала:
"""

    await message.answer(md(text), reply_markup=kb)


@dp.message(Command("courses"))
@rate_limit()
@require_auth()
async def cmd_courses(message: Message, user: Dict):
    """Обработчик /courses (только для авторизованных)"""
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
            await message.answer(md("❌ *Недостаточно прав*\n\nУ вас нет доступа к списку дисциплин\\."))
            return
        else:
            await message.answer(md("⚠️ *Ошибка при получении дисциплин*"))
            return

    if not result or "courses" not in result:
        await message.answer(md("📭 *Дисциплины не найдены*"))
        return

    courses = result["courses"]

    text = """
📚 *Доступные дисциплины*

"""

    for course in courses:
        text += f"• *{course['name']}* \\(ID: {course['id']}\\)\n"
        text += f"  {course['description']}\n\n"

    await message.answer(md(text))


@dp.message(Command("starttest"))
@rate_limit()
@require_auth()
async def cmd_starttest(message: Message, user: Dict):
    """Обработчик /starttest <id> (только для авторизованных)"""
    command_text = message.text or ""
    parts = command_text.split()

    if len(parts) < 2:
        await message.answer(md("❌ *Укажите ID теста*\n\nИспользование: `/starttest <ID_теста>`"))
        return

    try:
        test_id = int(parts[1])
    except ValueError:
        await message.answer(md("❌ *Неверный формат ID*\n\nID должен быть числом\\."))
        return

    # Запускаем тест через Core Service
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
            await message.answer(md("❌ *Недостаточно прав*\n\nУ вас нет доступа к этому тесту\\."))
            return
        elif result.get("status") == 418:
            await message.answer(md("🚫 *Пользователь заблокирован*\n\nДоступ к системе ограничен\\."))
            return
        else:
            await message.answer(md("⚠️ *Ошибка при запуске теста*"))
            return

    if not result:
        await message.answer(md("⚠️ *Не удалось начать тест*"))
        return

    # Сохраняем контекст теста
    await redis_client.setex(
        f"test_context:{user.get('chat_id')}",
        3600,
        json.dumps({
            "attempt_id": result.get("attempt_id"),
            "test_id": test_id,
            "questions": result.get("questions", []),
            "current_question": 0,
            "started_at": datetime.utcnow().isoformat()
        })
    )

    # Показываем первый вопрос
    questions = result.get("questions", [])
    if questions:
        question = questions[0]
        text = f"""
🎯 *Тест начат\\!*

*Вопрос 1 из {len(questions)}:*
{question['text']}

1\\. {question['options'][0]}
2\\. {question['options'][1]}
3\\. {question['options'][2]}

Отправьте номер правильного ответа \\(1\\-3\\)\\.
"""
        await message.answer(md(text))


@dp.message(Command("profile"))
@rate_limit()
@require_auth()
async def cmd_profile(message: Message, user: Dict):
    """Обработчик /profile"""
    user_id = user.get("user_id", "Неизвестно")
    email = user.get("email", "Неизвестно")

    text = f"""
👤 *Профиль пользователя*

*ID:* `{user_id}`
*Email:* {email}
*Авторизован:* {user.get('authorized_at', 'Неизвестно')}

━━━━━━━━━━━━━━━━━━
📊 *Статистика*
━━━━━━━━━━━━━━━━━━
• Пройдено тестов: 0
• Средний балл: 0%
• Активных попыток: 0

*Данные загружаются из Core Service\\...*
"""

    await message.answer(md(text))


@dp.message(Command("debug"))
@rate_limit()
async def cmd_debug(message: Message):
    """Отладочная команда"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    text = f"""
🐛 *Отладочная информация*

*Chat ID:* `{chat_id}`
*Пользователь в Redis:* {"Да" if user else "Нет"}

*Статус:* {user.get('status') if user else 'UNKNOWN'}
*User ID:* {user.get('user_id') if user else 'Нет'}
"""

    await message.answer(md(text))


# =========================
# CALLBACK HANDLERS
# =========================

@dp.callback_query(F.data.startswith("cmd_"))
async def callback_command(callback: CallbackQuery):
    """Обработчик callback команд"""
    command = callback.data[4:]  # Убираем "cmd_"

    if command == "login":
        await cmd_login(callback.message)
    elif command == "tests":
        await cmd_tests(callback.message)

    await callback.answer()


@dp.callback_query(F.data.startswith("check_auth_"))
async def callback_check_auth(callback: CallbackQuery):
    """Проверка статуса авторизации"""
    login_token = callback.data[11:]  # Убираем "check_auth_"

    # Проверяем токен в Auth Service
    result = await auth_service.check_login_token(login_token)

    if not result:
        await callback.answer("❌ Токен не найден или истек")
    elif result.get("status") == "pending":
        await callback.answer("⏳ Ожидание подтверждения входа")
    elif result.get("status") == "denied":
        await callback.answer("❌ Авторизация отклонена")
    elif result.get("status") == "granted":
        # Авторизация успешна
        user_data = result.get("user", {})
        access_token = result["access_token"]
        refresh_token = result["refresh_token"]

        # Сохраняем пользователя как AUTHORIZED
        await set_user_authorized(
            callback.from_user.id,
            access_token,
            refresh_token,
            user_data.get("id"),
            user_data.get("email")
        )

        await callback.answer("✅ Авторизация успешна!")

        # Обновляем сообщение
        await callback.message.edit_text(
            md(f"✅ *Авторизация завершена\\!*\n\nДобро пожаловать, {user_data.get('email')}"),
            reply_markup=None
        )

    await callback.message.edit_reply_markup(reply_markup=None)


@dp.callback_query(F.data.startswith("show_token_"))
async def callback_show_token(callback: CallbackQuery):
    """Показать токен для ручного ввода"""
    login_token = callback.data[11:]  # Убираем "show_token_"

    await callback.answer(
        f"Код для ввода в веб-клиенте:\n\n{login_token}",
        show_alert=True
    )


@dp.callback_query(F.data.startswith("start_test_"))
async def callback_start_test(callback: CallbackQuery):
    """Начать тест через inline-кнопку"""
    try:
        test_id = int(callback.data[11:])  # Убираем "start_test_"

        # Получаем пользователя
        user = await get_user(callback.from_user.id)
        if not user or user.get("status") != UserStatus.AUTHORIZED:
            await callback.answer("❌ Требуется авторизация")
            return

        # Запускаем тест
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

        # Сохраняем контекст
        await redis_client.setex(
            f"test_context:{callback.from_user.id}",
            3600,
            json.dumps({
                "attempt_id": result.get("attempt_id"),
                "test_id": test_id,
                "questions": result.get("questions", []),
                "current_question": 0,
                "started_at": datetime.utcnow().isoformat()
            })
        )

        # Показываем первый вопрос
        questions = result.get("questions", [])
        if questions:
            question = questions[0]
            text = f"""
🎯 *Тест начат\\!*

*Вопрос 1 из {len(questions)}:*
{question['text']}

1\\. {question['options'][0]}
2\\. {question['options'][1]}
3\\. {question['options'][2]}

Отправьте номер правильного ответа \\(1\\-3\\)\\.
"""
            await callback.message.edit_text(md(text))

        await callback.answer()

    except Exception as e:
        logger.error(f"Error starting test: {e}")
        await callback.answer("❌ Ошибка при запуске теста")


# =========================
# BACKGROUND TASKS (по ТЗ)
# =========================

async def check_anonymous_users_task():
    """Циклическая проверка anonymous пользователей (каждые 30 секунд)"""
    logger.info("Starting anonymous users check task...")

    while True:
        try:
            anonymous_users = await get_all_anonymous_users()

            for user in anonymous_users:
                login_token = user.get("login_token")
                if not login_token:
                    continue

                # Проверяем статус токена в Auth Service
                result = await auth_service.check_login_token(login_token)

                if not result:
                    # Токен не найден или истек
                    await delete_user(user["chat_id"])
                    continue

                if result.get("status") == "denied":
                    # Пользователь отказался от авторизации
                    await delete_user(user["chat_id"])
                    try:
                        await bot.send_message(
                            user["chat_id"],
                            md("❌ *Авторизация отклонена*\n\nВы отказались от входа в систему\\.")
                        )
                    except:
                        pass
                    continue

                if result.get("status") == "granted":
                    # Авторизация успешна
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

                    # Отправляем уведомление
                    try:
                        await bot.send_message(
                            user["chat_id"],
                            md(f"✅ *Авторизация успешно завершена\\!*\n\nДобро пожаловать, {user_data.get('email')}")
                        )
                    except:
                        pass

        except Exception as e:
            logger.error(f"Error in check_anonymous_users_task: {e}")

        await asyncio.sleep(30)  # Каждые 30 секунд по ТЗ


async def check_notifications_task():
    """Циклическая проверка уведомлений (каждые 60 секунд)"""
    logger.info("Starting notifications check task...")

    while True:
        try:
            authorized_users = await get_all_authorized_users()

            for user in authorized_users:
                access_token = user.get("access_token")
                if not access_token:
                    continue

                # Получаем уведомления из Core Service
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
                                md(f"📢 *{notification.get('title', 'Уведомление')}*\n\n{notification.get('message', '')}")
                            )
                        except:
                            pass

        except Exception as e:
            logger.error(f"Error in check_notifications_task: {e}")

        await asyncio.sleep(60)  # Каждые 60 секунд


# =========================
# MESSAGE HANDLER
# =========================

@dp.message()
@rate_limit()
async def handle_message(message: Message):
    """Обработчик всех сообщений"""
    chat_id = message.chat.id
    text = message.text or ""

    # Проверяем, есть ли активный тест
    context_data = await redis_client.get(f"test_context:{chat_id}")
    if context_data:
        await handle_test_answer(message, json.loads(context_data))
        return

    # Если сообщение не команда, показываем справку
    if not text.startswith('/'):
        await message.answer(md("🤖 *Неизвестная команда*\n\nИспользуйте /help для просмотра доступных команд\\."))


async def handle_test_answer(message: Message, context: Dict):
    """Обработка ответа на вопрос теста"""
    chat_id = message.chat.id
    current_q = context.get("current_question", 0)
    questions = context.get("questions", [])

    if current_q >= len(questions):
        # Тест завершен
        await redis_client.delete(f"test_context:{chat_id}")
        await message.answer(md("🎉 *Тест завершен\\!*\n\nРезультаты будут доступны в профиле\\."))
        return

    # Проверяем ответ
    try:
        answer = int(message.text.strip())
        if answer < 1 or answer > 3:
            raise ValueError
    except:
        await message.answer(md("❌ *Отправьте число от 1 до 3*"))
        return

    # Сохраняем ответ
    if "answers" not in context:
        context["answers"] = {}
    context["answers"][current_q] = answer - 1

    # Переходим к следующему вопросу
    context["current_question"] = current_q + 1

    if current_q + 1 < len(questions):
        # Сохраняем обновленный контекст
        await redis_client.setex(
            f"test_context:{chat_id}",
            3600,
            json.dumps(context)
        )

        # Показываем следующий вопрос
        question = questions[current_q + 1]
        text = f"""
*Вопрос {current_q + 2} из {len(questions)}:*
{question['text']}

1\\. {question['options'][0]}
2\\. {question['options'][1]}
3\\. {question['options'][2]}

Отправьте номер правильного ответа \\(1\\-3\\)\\.
"""
        await message.answer(md(text))
    else:
        # Тест завершен
        await redis_client.delete(f"test_context:{chat_id}")

        # Подсчитываем результаты (заглушка)
        correct = 0
        for i, q in enumerate(questions):
            if context["answers"].get(i) == q.get("correct", -1):
                correct += 1

        score = int((correct / len(questions)) * 100) if questions else 0

        text = f"""
🎉 *Тест завершен\\!*

*Результат:* {score}%
*Правильных ответов:* {correct} из {len(questions)}

🏆 *Отличная работа\\!*
"""
        await message.answer(md(text))


async def handle_token_refresh(message: Message, user: Dict):
    """Обработка обновления токена"""
    refresh_token = user.get("refresh_token")

    if not refresh_token:
        await message.answer(md("❌ *Токен устарел*\n\nПожалуйста, выполните вход заново\\."))
        await delete_user(message.chat.id)
        return

    # Пытаемся обновить токен
    result = await auth_service.refresh_tokens(refresh_token)

    if not result:
        await message.answer(md("❌ *Сессия истекла*\n\nПожалуйста, выполните вход заново\\."))
        await delete_user(message.chat.id)
        return

    # Обновляем токены в Redis
    user["access_token"] = result["access_token"]
    user["refresh_token"] = result["refresh_token"]
    await save_user(message.chat.id, user)

    await message.answer(md("🔄 *Токен обновлен*\n\nПовторите запрос\\."))


# =========================
# TEST COMMANDS (для отладки)
# =========================

@dp.message(Command("simulate_login"))
@rate_limit()
async def cmd_simulate_login(message: Message):
    """Симуляция успешной авторизации (для тестов)"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user or user.get("status") != UserStatus.ANONYMOUS:
        await message.answer(md("❌ *Сначала выполните /login*"))
        return

    login_token = user.get("login_token")
    if not login_token:
        await message.answer(md("❌ *Login token не найден*"))
        return

    # Имитируем успешную авторизацию
    await auth_service.simulate_login_granted(login_token)

    await message.answer(md("✅ *Авторизация имитирована*\n\nНажмите 'Проверить статус' или подождите 30 секунд\\."))


# =========================
# MAIN
# =========================

async def main():
    """Главная функция"""
    logger.info("🤖 Telegram bot starting...")

    # Запускаем фоновые задачи
    background_tasks = [
        asyncio.create_task(check_anonymous_users_task()),
        asyncio.create_task(check_notifications_task()),
    ]

    logger.info("✅ Background tasks started")
    logger.info(f"📊 Redis URL: {REDIS_URL}")
    logger.info("🚀 Bot is ready!")

    try:
        await dp.start_polling(bot)
    finally:
        # Отменяем фоновые задачи
        for task in background_tasks:
            task.cancel()

        # Закрываем HTTP сессию
        await http_client.close_session()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")