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
# AUTH SERVICE STUB - ИСПРАВЛЕННЫЙ
# =========================
class AuthServiceStub:
    def __init__(self):
        self.login_tokens = {}
        self.codes = {}
        self.confirmed_logins = set()  # Для заглушки: подтвержденные логины

    async def generate_login_url(self, login_token: str, provider: str = "code") -> str:
        code = secrets.randbelow(900000) + 100000

        if provider == "code":
            self.codes[code] = login_token

        self.login_tokens[login_token] = {
            "status": "pending",
            "provider": provider,
            "code": code if provider == "code" else None,
            "created_at": datetime.utcnow(),
            "user_agent": "telegram-bot",
            "confirmed": False  # Флаг подтверждения
        }

        if provider == "github":
            return "https://github.com/login/oauth/authorize"
        elif provider == "yandex":
            return "https://oauth.yandex.ru/authorize"
        else:
            return "https://t.me/cfutgbot"

    async def check_login_token(self, login_token: str) -> Optional[Dict]:
        """Проверка статуса токена - теперь с заглушкой для проверки"""
        if login_token not in self.login_tokens:
            return None

        token_data = self.login_tokens[login_token]

        # Заглушка: проверяем, был ли токен подтвержден
        if token_data.get("confirmed"):
            # Генерируем тестовые данные пользователя
            user_id = f"user_{secrets.token_hex(8)}"
            email = f"user_{login_token[:8]}@example.com"

            return {
                "status": "granted",
                "access_token": f"access_{secrets.token_hex(16)}",
                "refresh_token": f"refresh_{secrets.token_hex(16)}",
                "user": {
                    "id": user_id,
                    "email": email
                }
            }

        # Если не подтвержден, возвращаем pending
        return {"status": "pending"}

    async def confirm_login(self, login_token: str):
        """Подтверждение логина (заглушка для тестирования)"""
        if login_token in self.login_tokens:
            self.login_tokens[login_token]["confirmed"] = True
            self.login_tokens[login_token]["status"] = "granted"
            return True
        return False

    async def manual_auth_for_testing(self, login_token: str):
        """Ручная авторизация для тестирования (вызывается из /test_auth)"""
        if login_token in self.login_tokens:
            self.login_tokens[login_token]["confirmed"] = True
            self.login_tokens[login_token]["status"] = "granted"
            return True
        return False


auth_service = AuthServiceStub()


# =========================
# CORE SERVICE STUB - УЛУЧШЕННЫЙ ДЛЯ ПРОФИЛЯ И ТЕСТОВ
# =========================
class CoreServiceStub:
    async def get_tests(self, access_token: str) -> List[Dict]:
        """Получить список доступных тестов (заглушка)"""
        return [
            {"id": 1, "name": "Python Basics", "description": "Основы программирования на Python",
             "questions_count": 10, "active": True},
            {"id": 2, "name": "Async IO", "description": "Асинхронное программирование в Python", "questions_count": 8,
             "active": True},
            {"id": 3, "name": "Docker", "description": "Контейнеризация и Docker", "questions_count": 12,
             "active": False},
            {"id": 4, "name": "Базы данных", "description": "SQL и NoSQL базы данных", "questions_count": 15,
             "active": True},
            {"id": 5, "name": "Веб-разработка", "description": "Основы HTML, CSS, JavaScript", "questions_count": 20,
             "active": True}
        ]

    async def get_user_profile(self, user_data: Dict) -> Dict:
        """Получить профиль пользователя (заглушка на основе данных из Redis)"""
        user_id = user_data.get("user_id", "")
        email = user_data.get("email", "")

        # Генерируем фиктивные данные на основе email
        if "test" in email:
            name = "Тестовый Пользователь"
            role = "student"
            created_at = datetime.now().strftime("%Y-%m-%d")
            completed_tests = 3
            average_score = 78.5
        else:
            # Извлекаем имя из email
            email_prefix = email.split("@")[0] if "@" in email else "user"
            name = f"Пользователь {email_prefix.capitalize()}"
            role = "student"
            created_at = "2024-01-15"
            completed_tests = 5
            average_score = 85.0

        return {
            "id": user_id,
            "email": email,
            "name": name,
            "role": role,
            "created_at": created_at,
            "completed_tests": completed_tests,
            "average_score": average_score,
            "last_active": datetime.now().strftime("%Y-%m-%d %H:%M")
        }

    async def get_test_details(self, test_id: int, access_token: str) -> Dict:
        """Получить детали теста (заглушка)"""
        tests_data = {
            1: {"name": "Python Basics", "description": "Тест по основам Python", "duration": 30, "max_score": 100},
            2: {"name": "Async IO", "description": "Асинхронное программирование", "duration": 25, "max_score": 100},
            3: {"name": "Docker", "description": "Контейнеризация Docker", "duration": 40, "max_score": 100},
            4: {"name": "Базы данных", "description": "SQL и NoSQL базы данных", "duration": 35, "max_score": 100},
            5: {"name": "Веб-разработка", "description": "Основы веб-разработки", "duration": 45, "max_score": 100}
        }

        return tests_data.get(test_id, {"name": f"Тест {test_id}", "description": "Описание теста", "duration": 30,
                                        "max_score": 100})


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
        async def wrapper(event, *args, **kwargs):
            # Получаем chat_id в зависимости от типа события
            if isinstance(event, Message):
                chat_id = event.chat.id
            elif isinstance(event, CallbackQuery):
                chat_id = event.message.chat.id
            else:
                return

            user = await get_user(chat_id)
            if not user or user.get("status") != UserStatus.AUTHORIZED:
                try:
                    if isinstance(event, Message):
                        await bot.send_message(
                            chat_id,
                            "❌ <b>Требуется авторизация</b>\n\nИспользуйте /login для входа."
                        )
                    elif isinstance(event, CallbackQuery):
                        await event.answer("❌ Требуется авторизация", show_alert=True)
                except:
                    pass
                return
            return await handler(event, user, *args, **kwargs)

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
            if token_data.get("code"):
                code = token_data["code"]

        if provider == "code":
            code_text = f"<b>Код: <code>{code}</code></b>" if code else ""
            text = f"""
🔐 <b>Ожидание авторизации через код</b>

Для завершения авторизации введите код в веб-клиенте:

{code_text}

Нажмите "Проверить статус" после ввода кода.
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

<b>Основные команды:</b>
/start — начало работы
/help — эта справка
/status — статус системы

<b>Авторизация:</b>
/login — вход через код/GitHub/Яндекс
/logout — выход
/logout all=true — выход со всех устройств

<b>Дисциплины и тесты:</b>
/courses — список дисциплин
/tests — список тестов с кнопками для начала

<b>Профиль:</b>
/profile — информация о пользователе

<b>Технические команды:</b>
/services — информация о сервисах
/debug — отладочная информация
/ping — проверка работы бота
/echo — эхо-команда

<b>Команды для тестирования:</b>
/test_auth — быстрая авторизация (для тестирования)
"""
    await message.answer(help_text)


# =========================
# ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ - ЗАГЛУШКА
# =========================
@dp.message(Command("profile"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_profile(message: Message, user: Dict):
    """Информация о пользователе - заглушка на основе данных из Redis"""
    chat_id = message.chat.id
    current_user = await get_user(chat_id)

    if not current_user:
        await message.answer("❌ <b>Пользователь не найден</b>")
        return

    # Получаем профиль из заглушки
    profile = await core_service.get_user_profile(current_user)

    # Форматируем дату авторизации
    auth_date = "Неизвестно"
    if current_user.get("authorized_at"):
        try:
            auth_dt = datetime.fromisoformat(current_user["authorized_at"].replace('Z', '+00:00'))
            auth_date = auth_dt.strftime("%d.%m.%Y %H:%M")
        except:
            auth_date = current_user["authorized_at"]

    text = f"""
👤 <b>Профиль пользователя</b>

<b>Основная информация:</b>
📧 <b>Email:</b> {profile.get('email', 'Неизвестно')}
👤 <b>Имя:</b> {profile.get('name', 'Неизвестно')}
🎭 <b>Роль:</b> {profile.get('role', 'student')}
📅 <b>Дата регистрации:</b> {profile.get('created_at', 'Неизвестно')}
🔑 <b>ID пользователя:</b> <code>{profile.get('id', 'Неизвестно')}</code>

<b>Статистика обучения:</b>
✅ <b>Пройдено тестов:</b> {profile.get('completed_tests', 0)}
🏆 <b>Средний балл:</b> {profile.get('average_score', 0)}%
📊 <b>Последняя активность:</b> {profile.get('last_active', 'Неизвестно')}

<b>Сессия в Telegram:</b>
🤖 <b>Авторизован:</b> {auth_date}
🔐 <b>Статус:</b> 🟢 Активен
"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мои результаты", callback_data="my_results")],
        [InlineKeyboardButton(text="⚙️ Настройки профиля", callback_data="profile_settings")],
        [InlineKeyboardButton(text="🔄 Обновить данные", callback_data="refresh_profile")]
    ])

    await message.answer(text, reply_markup=kb)


# =========================
# СПИСОК ТЕСТОВ С КНОПКАМИ
# =========================
@dp.message(Command("tests"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_tests(message: Message, user: Dict):
    """Список доступных тестов с кнопками для начала"""
    chat_id = message.chat.id
    current_user = await get_user(chat_id)

    if not current_user:
        await message.answer("❌ <b>Требуется авторизация</b>\n\nИспользуйте /login для входа.")
        return

    # Получаем список тестов из заглушки
    tests = await core_service.get_tests(current_user.get("access_token", ""))

    # Активные тесты
    active_tests = [t for t in tests if t.get("active")]
    inactive_tests = [t for t in tests if not t.get("active")]

    # Формируем текст
    text = "📚 <b>Доступные тесты</b>\n\n"

    if active_tests:
        text += "🟢 <b>Активные тесты:</b>\n"
        for test in active_tests:
            text += f"  • <b>{test['name']}</b>\n"
            text += f"    📝 {test['description']}\n"
            text += f"    ❓ Вопросов: {test.get('questions_count', 0)}\n\n"

    if inactive_tests:
        text += "🔴 <b>Неактивные тесты:</b>\n"
        for test in inactive_tests:
            text += f"  • <b>{test['name']}</b> (недоступен)\n"

    # Создаем кнопки для активных тестов
    buttons = []
    for test in active_tests:
        buttons.append([
            InlineKeyboardButton(
                text=f"▶️ Начать тест: {test['name']}",
                callback_data=f"start_test_{test['id']}"
            )
        ])

    # Добавляем информационные кнопки
    buttons.append([
        InlineKeyboardButton(text="📊 Мои результаты", callback_data="my_test_results"),
        InlineKeyboardButton(text="🔄 Обновить список", callback_data="refresh_tests")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if not active_tests:
        text += "\n😔 <b>В данный момент нет активных тестов для прохождения.</b>"
        kb = None

    await message.answer(text, reply_markup=kb)


# =========================
# НАЧАЛО ТЕСТА ПО КНОПКЕ
# =========================
@dp.callback_query(F.data.startswith("start_test_"))
@require_auth()
async def callback_start_test(callback: CallbackQuery, user: Dict):
    """Обработчик начала теста по кнопке"""
    try:
        test_id = int(callback.data[11:])
        await callback.answer(f"🚀 Начинаем тест #{test_id}")

        # Получаем детали теста из заглушки
        test_details = await core_service.get_test_details(test_id, user.get("access_token", ""))

        # Сохраняем контекст теста в Redis
        test_context = {
            "test_id": test_id,
            "test_name": test_details.get("name", f"Тест {test_id}"),
            "started_at": datetime.now().isoformat(),
            "current_question": 0,
            "answers": {},
            "user_id": user.get("user_id"),
            "chat_id": callback.message.chat.id
        }

        await redis_client.setex(
            f"test_context:{callback.message.chat.id}",
            3600,  # 1 час на прохождение
            json.dumps(test_context)
        )

        # Отправляем первый вопрос (заглушка)
        text = f"""
🧪 <b>Начинаем тест: {test_details.get('name', f'Тест {test_id}')}</b>

<b>Описание:</b> {test_details.get('description', 'Описание теста')}
<b>Длительность:</b> {test_details.get('duration', 30)} минут
<b>Максимальный балл:</b> {test_details.get('max_score', 100)}

<b>Первый вопрос:</b>

1. Что такое Python?
   a) Язык программирования
   b) Змея
   c) Оба варианта верны

Отправьте номер правильного ответа (1-3).
"""

        await callback.message.answer(text)

    except ValueError:
        await callback.answer("❌ Ошибка: неверный ID теста")
    except Exception as e:
        logger.error(f"Error starting test: {e}")
        await callback.answer("❌ Ошибка при начале теста")


# =========================
# ОБРАБОТКА ОТВЕТОВ НА ТЕСТ
# =========================
@dp.message()
@rate_limit()
@safe_send_message
async def handle_test_answers(message: Message):
    """Обработка ответов на вопросы теста"""
    chat_id = message.chat.id
    text = message.text or ""

    # Проверяем, есть ли активный тест
    context_data = await redis_client.get(f"test_context:{chat_id}")
    if not context_data:
        # Если теста нет, проверяем команды
        if text.startswith('/'):
            return  # Обработка команд будет в других хендлерах
        else:
            await message.answer("🤖 <b>Неизвестная команда</b>\n\nИспользуйте /help для просмотра доступных команд.")
        return

    # Обрабатываем ответ на вопрос теста
    try:
        context = json.loads(context_data)
        current_q = context.get("current_question", 0)

        # Пример вопросов (в реальной системе брались бы из базы)
        questions = [
            {
                "text": "Что такое Python?",
                "options": ["Язык программирования", "Змея", "Оба варианта верны"],
                "correct": 2  # Номер правильного ответа (0-based)
            },
            {
                "text": "Что такое Docker?",
                "options": ["Контейнеризация", "Игра", "Операционная система"],
                "correct": 0
            },
            {
                "text": "Что такое API?",
                "options": ["Интерфейс программирования", "Аппаратный интерфейс", "Оба варианта"],
                "correct": 0
            }
        ]

        # Проверяем ответ
        try:
            answer = int(text.strip())
            if answer < 1 or answer > 3:
                raise ValueError
        except:
            await message.answer("❌ <b>Отправьте число от 1 до 3</b>")
            return

        # Сохраняем ответ
        context["answers"][current_q] = answer - 1  # Сохраняем как 0-based
        context["current_question"] = current_q + 1

        # Проверяем, закончен ли тест
        if current_q + 1 >= len(questions):
            # Тест завершен
            await redis_client.delete(f"test_context:{chat_id}")

            # Подсчитываем результаты
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

Ваши ответы сохранены. Результаты будут доступны в профиле.
"""
            await message.answer(text)
        else:
            # Показываем следующий вопрос
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

    except Exception as e:
        logger.error(f"Error processing test answer: {e}")
        await message.answer("❌ <b>Ошибка при обработке ответа</b>")


# =========================
# ОСТАЛЬНЫЕ КОМАНДЫ (БЕЗ ИЗМЕНЕНИЙ)
# =========================
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

<b>Ваш статус:</b>
{user_status}{user_details}

<b>Статистика:</b>
⏰ <b>Текущее время:</b> {current_time}
👥 <b>Активных пользователей:</b> {active_users_count}
📊 <b>Выполнено команд:</b> {commands_count}

<b>Сервисы:</b>
• Redis — {redis_status}
• Telegram Bot — 🟢 онлайн

<b>Модули:</b>
• Auth Service — 🟡 заглушка
• Core Service — 🟡 заглушка
• Web Client — 🟡 заглушка
"""
    await message.answer(text)


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


@dp.message(Command("services"))
@rate_limit()
@safe_send_message
async def cmd_services(message: Message):
    text = """
🧩 <b>Архитектура системы</b>

<b>Telegram Bot (этот модуль)</b>
• Обработка команд пользователей
• Управление состоянием через Redis
• Отображение результатов тестов
• Циклическая проверка статуса авторизации

<b>Auth Service</b>
• Авторизация через GitHub, Яндекс ID, Code
• Выдача JWT токенов
• Управление сессиями пользователей
• Обновление и валидация токенов

<b>Core Service</b>
• Логика тестирования и оценки
• Управление дисциплинами и тестами
• Хранение результатов
• Проверка разрешений и доступов

<b>Web Client</b>
• Веб-интерфейс системы
• Управление для преподавателей
• Создание и редактирование тестов
• Аналитика и отчеты

<b>Базы данных</b>
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


@dp.message(Command("test_auth"))
@rate_limit()
@safe_send_message
async def cmd_test_auth(message: Message):
    """Быстрая авторизация для тестирования (минуя веб-клиент)"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await message.answer(f"✅ <b>Вы уже авторизованы как {user.get('email')}</b>")
        return

    # Создаем фейковые данные для авторизации
    user_id = f"test_user_{secrets.token_hex(6)}"
    email = f"test_{chat_id}@example.com"
    access_token = f"test_access_{secrets.token_hex(16)}"
    refresh_token = f"test_refresh_{secrets.token_hex(16)}"

    # Устанавливаем пользователя как авторизованного
    await set_user_authorized(chat_id, access_token, refresh_token, user_id, email)

    text = f"""
✅ <b>Тестовая авторизация успешна!</b>

Вы авторизованы для тестирования:
📧 <b>Email:</b> {email}
👤 <b>User ID:</b> {user_id}

<b>Доступные команды:</b>
• /tests — список тестов
• /courses — список дисциплин
• /profile — ваш профиль
• /logout — выход

<b>Примечание:</b> Это тестовая авторизация без использования сервисов.
"""
    await message.answer(text)


# =========================
# CALLBACK HANDLERS (ОСТАЛЬНЫЕ)
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
        [InlineKeyboardButton(text="🚀 Быстрая авторизация (тест)", callback_data="test_auth_quick")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.callback_query(F.data.startswith("check_auth_"))
async def callback_check_auth(callback: CallbackQuery):
    """Проверка статуса авторизации - теперь с заглушкой"""
    login_token = callback.data[11:]
    result = await auth_service.check_login_token(login_token)

    if not result:
        await callback.answer("❌ Токен не найден или истек")
    elif result.get("status") == "pending":
        # Заглушка: сообщаем, что авторизация еще не подтверждена
        await callback.answer("⏳ Ожидание подтверждения авторизации в веб-клиенте")

        # Добавляем кнопку для тестирования
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
                [InlineKeyboardButton(text="🚀 Тест: Подтвердить авторизацию",
                                      callback_data=f"confirm_auth_{login_token}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
            ])
            await callback.message.edit_reply_markup(reply_markup=kb)
        except:
            pass
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


@dp.callback_query(F.data.startswith("confirm_auth_"))
async def callback_confirm_auth(callback: CallbackQuery):
    """Подтверждение авторизации для тестирования (заглушка)"""
    login_token = callback.data[13:]

    # Подтверждаем авторизацию в заглушке
    success = await auth_service.confirm_login(login_token)

    if success:
        # Теперь проверяем токен еще раз
        result = await auth_service.check_login_token(login_token)

        if result and result.get("status") == "granted":
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

            await callback.answer("✅ Авторизация подтверждена и успешна!")
            await callback.message.edit_text(
                f"✅ <b>Авторизация завершена!</b>\n\nДобро пожаловать, {user_data.get('email')}\n\n<em>Примечание: использована заглушка для тестирования</em>",
                reply_markup=None
            )
        else:
            await callback.answer("❌ Ошибка подтверждения")
    else:
        await callback.answer("❌ Токен не найден")


@dp.callback_query(F.data == "test_auth_quick")
async def callback_test_auth_quick(callback: CallbackQuery):
    """Быстрая тестовая авторизация через callback"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    # Создаем фейковые данные для авторизации
    user_id = f"test_user_{secrets.token_hex(6)}"
    email = f"test_{chat_id}@example.com"
    access_token = f"test_access_{secrets.token_hex(16)}"
    refresh_token = f"test_refresh_{secrets.token_hex(16)}"

    # Устанавливаем пользователя как авторизованного
    await set_user_authorized(chat_id, access_token, refresh_token, user_id, email)

    await callback.answer("✅ Тестовая авторизация успешна!")
    await callback.message.edit_text(
        f"✅ <b>Тестовая авторизация успешна!</b>\n\nДобро пожаловать, {email}\n\n<em>Использована тестовая авторизация без веб-клиента</em>",
        reply_markup=None
    )


@dp.callback_query(F.data == "cancel_auth")
async def callback_cancel_auth(callback: CallbackQuery):
    chat_id = callback.from_user.id
    await delete_user(chat_id)
    await callback.answer("❌ Авторизация отменена")
    await callback.message.edit_text("🚪 <b>Авторизация отменена</b>", reply_markup=None)


# =========================
# BACKGROUND TASK - ТОЛЬКО ДЛЯ ОЧИСТКИ
# =========================
async def check_anonymous_users_task():
    """Циклическая проверка anonymous пользователей - только удаление просроченных"""
    while True:
        try:
            keys = await redis_client.keys("user:*")
            for key in keys:
                data = await redis_client.get(key)
                if data:
                    user = json.loads(data)
                    if user.get("status") == UserStatus.ANONYMOUS:
                        created_at_str = user.get("created_at")
                        if created_at_str:
                            try:
                                created_at = datetime.fromisoformat(created_at_str)
                                if (datetime.utcnow() - created_at).seconds > 300:  # 5 минут
                                    # Удаляем просроченного пользователя
                                    chat_id = int(key.split(":")[1])
                                    await delete_user(chat_id)
                            except:
                                pass
        except Exception as e:
            logger.error(f"Error in check_anonymous_users_task: {e}")

        await asyncio.sleep(30)  # Проверка каждые 30 секунд


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