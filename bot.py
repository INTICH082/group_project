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
# STATISTICS
# =========================
class Statistics:
    def __init__(self):
        self.commands_count = 0
        self.active_users = set()

    def increment_commands(self):
        self.commands_count += 1

    def add_active_user(self, user_id: int):
        self.active_users.add(user_id)

    def remove_active_user(self, user_id: int):
        self.active_users.discard(user_id)

    def get_active_users_count(self):
        return len(self.active_users)


stats = Statistics()


# =========================
# SIMPLE REDIS
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
# AUTH SERVICE STUB
# =========================
class AuthServiceStub:
    def __init__(self):
        self.login_tokens = {}
        self.codes = {}

    async def generate_login_url(self, login_token: str, provider: str = "code") -> str:
        code = secrets.randbelow(900000) + 100000

        if provider == "code":
            self.codes[code] = login_token

        self.login_tokens[login_token] = {
            "status": "pending",
            "provider": provider,
            "code": code if provider == "code" else None,
            "created_at": datetime.utcnow(),
            "checked": False
        }

        if provider == "github":
            return "https://github.com/login/oauth/authorize"
        elif provider == "yandex":
            return "https://oauth.yandex.ru/authorize"
        else:
            return "https://t.me/cfutgbot"

    async def check_login_token(self, login_token: str) -> Optional[Dict]:
        if login_token not in self.login_tokens:
            return None

        token_data = self.login_tokens[login_token]

        # Автоматически подтверждаем через 2 секунды для тестирования
        if not token_data.get("checked") and (datetime.utcnow() - token_data["created_at"]).seconds > 2:
            token_data["status"] = "granted"
            token_data["checked"] = True

            return {
                "status": "granted",
                "access_token": f"access_{secrets.token_hex(16)}",
                "refresh_token": f"refresh_{secrets.token_hex(16)}",
                "user": {
                    "id": f"user_{secrets.token_hex(8)}",
                    "email": f"user_{login_token[:8]}@example.com"
                }
            }

        return {"status": token_data["status"]}

    async def simulate_manual_auth(self, login_token: str):
        """Имитация ручной авторизации (для тестирования)"""
        if login_token in self.login_tokens:
            self.login_tokens[login_token]["status"] = "granted"
            self.login_tokens[login_token]["checked"] = True


auth_service = AuthServiceStub()


# =========================
# CORE SERVICE STUB
# =========================
class CoreServiceStub:
    async def get_tests(self, access_token: str) -> List[Dict]:
        return [
            {"id": 1, "name": "Python Basics", "description": "Основы программирования на Python",
             "questions_count": 10, "active": True},
            {"id": 2, "name": "Async IO", "description": "Асинхронное программирование в Python", "questions_count": 8,
             "active": True},
            {"id": 3, "name": "Docker", "description": "Контейнеризация и Docker", "questions_count": 12,
             "active": False},
            {"id": 4, "name": "Базы данных", "description": "SQL и NoSQL базы данных", "questions_count": 15,
             "active": True}
        ]

    async def get_user_profile(self, access_token: str, user_id: str) -> Dict:
        return {
            "id": user_id,
            "email": f"user_{user_id[:8]}@example.com",
            "name": "Иван Иванов",
            "role": "student",
            "created_at": "2024-01-01T00:00:00",
            "completed_tests": 5,
            "average_score": 85.5
        }


core_service = CoreServiceStub()


# =========================
# DECORATORS
# =========================
async def check_rate_limit(chat_id: int, seconds: int = 2) -> bool:
    return True


def rate_limit(seconds: int = 2):
    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            stats.increment_commands()
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


def require_auth():
    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            user = await get_user(message.chat.id)
            if not user or user.get("status") != UserStatus.AUTHORIZED:
                await message.answer("❌ <b>Требуется авторизация</b>\n\nИспользуйте /login для входа.")
                return
            return await handler(message, user, *args, **kwargs)

        return wrapper

    return decorator


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
    stats.add_active_user(chat_id)


async def get_user_status(chat_id: int) -> UserStatus:
    user = await get_user(chat_id)
    if not user:
        return UserStatus.UNKNOWN
    return UserStatus(user.get("status", UserStatus.UNKNOWN))


async def get_all_authorized_users() -> List[Dict]:
    users = []
    try:
        keys = await redis_client.keys("user:*")
        for key in keys:
            data = await redis_client.get(key)
            if data:
                user = json.loads(data)
                if user.get("status") == UserStatus.AUTHORIZED:
                    try:
                        chat_id = int(key.split(":")[1])
                        user["chat_id"] = chat_id
                        users.append(user)
                    except:
                        pass
    except Exception as e:
        logger.error(f"Error getting authorized users: {e}")
    return users


# =========================
# COMMAND HANDLERS
# =========================
@dp.message(Command("start"))
@rate_limit()
@safe_send_message
async def cmd_start(message: Message):
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

        code = ""
        if login_token in auth_service.login_tokens:
            token_data = auth_service.login_tokens[login_token]
            if "code" in token_data and token_data["code"]:
                code = token_data["code"]

        if provider == "code":
            code_text = f"<b>Код: <code>{code}</code></b>" if code else ""
            text = f"""
🔐 <b>Ожидание авторизации через код</b>

Для завершения авторизации введите код в веб-клиенте:

{code_text}

Или нажмите "Проверить статус".
"""
        else:
            provider_name = "GitHub" if provider == "github" else "Яндекс ID" if provider == "yandex" else provider
            text = f"""
🔐 <b>Ожидание авторизации через {provider_name}</b>

Для завершения авторизации подтвердите вход в браузере.

Нажмите "Проверить статус" после подтверждения.
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

━━━━━━━━━━━━━━━━━━
🚀 <b>Основные команды</b>
━━━━━━━━━━━━━━━━━━
/start — начало работы  
/help — эта справка  
/status — статус системы  

━━━━━━━━━━━━━━━━━━
🔐 <b>Авторизация</b>
━━━━━━━━━━━━━━━━━━
/login — вход через код/GitHub/Яндекс  
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
/ping — проверка работы бота
/echo — эхо-команда
"""
    await message.answer(help_text)


@dp.message(Command("login"))
@rate_limit()
@safe_send_message
async def cmd_login(message: Message):
    """Показ выбора провайдера авторизации"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await message.answer(f"✅ <b>Вы уже авторизованы как {user.get('email')}</b>\n\nИспользуйте /logout для выхода.")
        return

    text = """
🔐 <b>Выберите способ авторизации:</b>

1. <b>GitHub</b> — вход через аккаунт GitHub
2. <b>Яндекс ID</b> — вход через Яндекс
3. <b>Code</b> — авторизация через код (веб-клиент)
"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 GitHub", callback_data="login_github")],
        [InlineKeyboardButton(text="🔗 Яндекс ID", callback_data="login_yandex")],
        [InlineKeyboardButton(text="🔢 Code", callback_data="login_code")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await message.answer(text, reply_markup=kb)


@dp.message(Command("logout"))
@rate_limit()
@safe_send_message
async def cmd_logout(message: Message):
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user:
        await message.answer("❌ <b>Вы не авторизованы</b>\n\nСначала выполните /login.")
        return

    if user.get("status") != UserStatus.AUTHORIZED:
        await delete_user(chat_id)
        await message.answer("🚪 <b>Процесс авторизации прерван</b>")
        return

    command_text = message.text or ""
    logout_all = "all=true" in command_text.lower()

    if logout_all:
        await message.answer("✅ <b>Выход выполнен со всех устройств</b>")
    else:
        await message.answer("🚪 <b>Вы вышли из системы</b>")

    stats.remove_active_user(chat_id)
    await delete_user(chat_id)


@dp.message(Command("status"))
@rate_limit()
@safe_send_message
async def cmd_status(message: Message):
    chat_id = message.chat.id
    user = await get_user(chat_id)

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not user:
        user_status = "❌ <b>Не авторизован</b>"
        user_details = ""
    elif user.get("status") == UserStatus.ANONYMOUS:
        user_status = "🟡 <b>Ожидание авторизации</b>"
        provider = user.get("provider", "code")
        provider_name = {
            "github": "GitHub",
            "yandex": "Яндекс ID",
            "code": "код"
        }.get(provider, provider)
        user_details = f"\n🔧 Способ входа: {provider_name}"
    else:
        user_status = "✅ <b>Авторизован</b>"
        email = user.get("email", "Неизвестно")
        user_details = f"\n📧 Email: {email}"

    authorized_users = await get_all_authorized_users()
    active_users_count = len(authorized_users)
    commands_count = stats.commands_count

    redis_status = "🟢 онлайн" if redis_client.connected else "🔴 оффлайн"

    text = f"""
📊 <b>Статус системы</b>

━━━━━━━━━━━━━━━━━━
👤 <b>Ваш статус</b>
━━━━━━━━━━━━━━━━━━
{user_status}{user_details}

━━━━━━━━━━━━━━━━━━
📈 <b>Статистика</b>
━━━━━━━━━━━━━━━━━━
⏰ <b>Текущее время:</b> {current_time}
👥 <b>Активных пользователей:</b> {active_users_count}
📊 <b>Выполнено команд:</b> {commands_count}

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
• Web Client — 🟡 заглушка
"""
    await message.answer(text)


@dp.message(Command("tests"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_tests(message: Message, user: Dict):
    tests = await core_service.get_tests(user.get("access_token", ""))

    text = "📚 <b>Доступные тесты</b>\n\n"
    buttons = []

    for test in tests:
        status = "🟢" if test.get("active") else "🔴"
        text += f"{status} <b>{test['name']}</b>\n"
        text += f"📝 {test['description']}\n"
        text += f"❓ Вопросов: {test.get('questions_count', 0)}\n\n"

        if test.get("active"):
            buttons.append([
                InlineKeyboardButton(
                    text=f"▶️ {test['name']}",
                    callback_data=f"start_test_{test['id']}"
                )
            ])

    if not buttons:
        text += "\n😔 <b>Нет активных тестов для прохождения</b>"

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer(text, reply_markup=kb)


@dp.message(Command("courses"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_courses(message: Message, user: Dict):
    text = """
🎓 <b>Доступные дисциплины</b>

1. <b>Программирование</b>
   • Основы программирования
   • Объектно-ориентированное программирование
   • Алгоритмы и структуры данных

2. <b>Базы данных</b>
   • SQL и реляционные БД
   • NoSQL базы данных
   • Оптимизация запросов

3. <b>Веб-разработка</b>
   • HTML/CSS/JavaScript
   • Backend разработка
   • Фреймворки

4. <b>DevOps</b>
   • Docker и контейнеризация
   • CI/CD
   • Мониторинг
"""
    await message.answer(text)


@dp.message(Command("profile"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_profile(message: Message, user: Dict):
    user_id = user.get("user_id", "")
    access_token = user.get("access_token", "")

    profile = await core_service.get_user_profile(access_token, user_id)

    text = f"""
👤 <b>Профиль пользователя</b>

<b>Основная информация:</b>
📧 <b>Email:</b> {profile.get('email', 'Неизвестно')}
👤 <b>Имя:</b> {profile.get('name', 'Неизвестно')}
🎭 <b>Роль:</b> {profile.get('role', 'student')}
📅 <b>Дата регистрации:</b> {profile.get('created_at', 'Неизвестно')}

<b>Статистика:</b>
✅ <b>Пройдено тестов:</b> {profile.get('completed_tests', 0)}
🏆 <b>Средний балл:</b> {profile.get('average_score', 0)}%

<b>Статус:</b> 🟢 Активен
"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мои результаты", callback_data="my_results")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
    ])

    await message.answer(text, reply_markup=kb)


@dp.message(Command("services"))
@rate_limit()
@safe_send_message
async def cmd_services(message: Message):
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
🔐 <b>Auth Service</b>
━━━━━━━━━━━━━━━━━━
• Авторизация через GitHub, Яндекс ID, Code
• Выдача JWT токенов
• Управление сессиями пользователей
• Обновление и валидация токенов

━━━━━━━━━━━━━━━━━━
⚙️ <b>Core Service</b>
━━━━━━━━━━━━━━━━━━
• Логика тестирования и оценки
• Управление дисциплинами и тестами
• Хранение результатов
• Проверка разрешений и доступов

━━━━━━━━━━━━━━━━━━
🌐 <b>Web Client</b>
━━━━━━━━━━━━━━━━━━
• Веб-интерфейс системы
• Управление для преподавателей
• Создание и редактирование тестов
• Аналитика и отчеты

━━━━━━━━━━━━━━━━━━
🗄️ <b>Базы данных</b>
━━━━━━━━━━━━━━━━━━
• PostgreSQL — основное хранилище
• Redis — кэш и сессии
• MongoDB — аналитика и логи
"""
    await message.answer(text)


@dp.message(Command("debug"))
@rate_limit()
@safe_send_message
async def cmd_debug(message: Message):
    chat_id = message.chat.id
    user = await get_user(chat_id)

    authorized_users = await get_all_authorized_users()

    text = f"""
🐛 <b>Отладочная информация</b>

<b>Система:</b>
• Chat ID: <code>{chat_id}</code>
• Redis: {"🟢 подключен" if redis_client.connected else "🔴 оффлайн"}
• Время: {datetime.now().strftime("%H:%M:%S")}

<b>Пользователь:</b>
• Статус: {user.get('status') if user else 'UNKNOWN'}
• User ID: {user.get('user_id') if user else 'Нет'}
• Email: {user.get('email') if user else 'Нет'}

<b>Статистика:</b>
• Активных пользователей: {len(authorized_users)}
• Выполнено команд: {stats.commands_count}
• Login tokens: {len(auth_service.login_tokens)}
"""
    await message.answer(text)


@dp.message(Command("ping"))
@rate_limit()
@safe_send_message
async def cmd_ping(message: Message):
    await message.answer("🏓 <b>Pong!</b>\n\n🤖 Бот работает корректно.\n⚡ Все системы в норме.")


@dp.message(Command("echo"))
@rate_limit()
@safe_send_message
async def cmd_echo(message: Message):
    text = message.text or ""
    if len(text) > 6:
        await message.answer(f"📢 <b>Эхо:</b>\n\n{text[6:]}")
    else:
        await message.answer("📢 <b>Напишите что-нибудь после /echo</b>\n\nПример: <code>/echo Привет, мир!</code>")


# =========================
# CALLBACK HANDLERS
# =========================
@dp.callback_query(F.data == "login")
async def callback_login(callback: CallbackQuery):
    await callback.answer()
    await cmd_login(callback.message)


@dp.callback_query(F.data.startswith("login_"))
async def callback_login_provider(callback: CallbackQuery):
    provider = callback.data[6:]  # github, yandex, code
    chat_id = callback.from_user.id

    if provider not in ["github", "yandex", "code"]:
        await callback.answer("❌ Неизвестный провайдер")
        return

    user = await get_user(chat_id)
    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, provider)

    auth_url = await auth_service.generate_login_url(login_token, provider)

    provider_names = {
        "github": "GitHub",
        "yandex": "Яндекс ID",
        "code": "код"
    }

    if provider == "code":
        code = auth_service.login_tokens[login_token]["code"]
        text = f"""
🔐 <b>Авторизация через код</b>

Для входа в систему введите код в веб-клиенте:

<b>Код: <code>{code}</code></b>

⏳ <b>Код действителен 5 минут</b>

После ввода кода нажмите "Проверить статус".
"""
    else:
        provider_name = provider_names[provider]
        text = f"""
🔐 <b>Авторизация через {provider_name}</b>

Для завершения авторизации перейдите по ссылке:

<a href="{auth_url}">Ссылка для авторизации через {provider_name}</a>

После подтверждения нажмите "Проверить статус".
"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


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

        try:
            await callback.message.edit_text(
                f"✅ <b>Авторизация завершена!</b>\n\nДобро пожаловать, {user_data.get('email')}",
                reply_markup=None
            )
        except:
            await callback.message.answer(
                f"✅ <b>Авторизация завершена!</b>\n\nДобро пожаловать, {user_data.get('email')}")


@dp.callback_query(F.data == "cancel_auth")
async def callback_cancel_auth(callback: CallbackQuery):
    chat_id = callback.from_user.id
    await delete_user(chat_id)
    await callback.answer("❌ Авторизация отменена")
    await callback.message.edit_text("🚪 <b>Авторизация отменена</b>", reply_markup=None)


@dp.callback_query(F.data.startswith("start_test_"))
@require_auth()
async def callback_start_test(callback: CallbackQuery, user: Dict):
    try:
        test_id = int(callback.data[11:])
        await callback.answer(f"🚀 Начинаем тест #{test_id}")

        # Здесь будет логика начала теста
        await callback.message.answer(f"🧪 <b>Начинаем тест #{test_id}</b>\n\nСкоро здесь будут вопросы...")

    except ValueError:
        await callback.answer("❌ Ошибка: неверный ID теста")


# =========================
# BACKGROUND TASK
# =========================
async def check_anonymous_users_task():
    """Циклическая проверка anonymous пользователей"""
    while True:
        try:
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
                                user_data = result.get("user", {})
                                access_token = result["access_token"]
                                refresh_token = result["refresh_token"]

                                try:
                                    chat_id = int(key.split(":")[1])
                                    await set_user_authorized(
                                        chat_id,
                                        access_token,
                                        refresh_token,
                                        user_data.get("id"),
                                        user_data.get("email")
                                    )

                                    await bot.send_message(
                                        chat_id,
                                        f"✅ <b>Авторизация успешно завершена!</b>\n\nДобро пожаловать, {user_data.get('email')}"
                                    )
                                except:
                                    pass
        except Exception as e:
            logger.error(f"Error in check_anonymous_users_task: {e}")

        await asyncio.sleep(5)


# =========================
# MESSAGE HANDLER
# =========================
@dp.message()
@rate_limit()
@safe_send_message
async def handle_message(message: Message):
    text = message.text or ""
    if not text.startswith('/'):
        await message.answer("🤖 <b>Неизвестная команда</b>\n\nИспользуйте /help для просмотра доступных команд.")


# =========================
# MAIN
# =========================
async def main():
    logger.info("🤖 Telegram bot starting...")

    await redis_client.connect()

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