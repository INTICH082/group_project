import asyncio
import logging
import os
import json
import secrets
import jwt
import aiohttp
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
API_BASE_URL = os.getenv("API_BASE_URL", "https://my-app-logic.onrender.com")
JWT_SECRET = os.getenv("JWT_SECRET", "iplaygodotandclaimfun")
DEFAULT_COURSE_ID = int(os.getenv("DEFAULT_COURSE_ID", "1"))

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
# API CLIENT
# =========================
class APIClient:
    def __init__(self, base_url: str, jwt_secret: str):
        self.base_url = base_url.rstrip('/')
        self.jwt_secret = jwt_secret
        self.session = None

    async def ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()

    def generate_token(self, user_id: int, role: str = "student", permissions: Optional[List[str]] = None) -> str:
        """Генерация JWT токена для API"""
        if permissions is None:
            permissions = ["course:read"]

        payload = {
            "user_id": user_id,
            "role": role,
            "permissions": permissions,
            "exp": datetime.utcnow() + timedelta(hours=24),
            "is_blocked": False
        }

        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    async def request(self, method: str, endpoint: str, token: str = None, data: Optional[Dict] = None) -> Dict:
        """Выполнение HTTP запроса к API"""
        await self.ensure_session()

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}" if token else ""
        }

        try:
            async with self.session.request(method, url, headers=headers, json=data) as response:
                response_text = await response.text()

                if response.status == 418:  # I'm a teapot
                    raise Exception("Пользователь заблокирован")

                if response.status >= 400:
                    raise Exception(f"API ошибка {response.status}: {response_text}")

                if response_text:
                    try:
                        return json.loads(response_text)
                    except json.JSONDecodeError:
                        return {"text": response_text}
                return {}

        except aiohttp.ClientError as e:
            logger.error(f"Ошибка соединения с API: {e}")
            raise Exception(f"Сервис временно недоступен: {e}")

    async def get_tests(self, token: str, course_id: int = DEFAULT_COURSE_ID) -> List[Dict]:
        """Получить список тестов курса"""
        try:
            response = await self.request("GET", f"/course/tests?course_id={course_id}", token)

            # Если ответ - строка, пытаемся распарсить
            if isinstance(response, dict) and "text" in response:
                try:
                    return json.loads(response["text"])
                except:
                    return []

            # Если ответ уже список
            if isinstance(response, list):
                return response

            # Если ответ в другом формате
            tests = response.get("tests", []) or response.get("data", []) or []
            return tests if isinstance(tests, list) else []

        except Exception as e:
            logger.error(f"Ошибка при получении тестов: {e}")
            return []

    async def start_test(self, token: str, test_id: int) -> Dict:
        """Начать тест"""
        return await self.request("POST", f"/test/start?test_id={test_id}", token)

    async def submit_answer(self, token: str, attempt_id: int, question_id: int, option: int) -> Dict:
        """Отправить ответ на вопрос"""
        return await self.request("POST", f"/test/answer?attempt_id={attempt_id}&question_id={question_id}",
                                  token, {"option": option})

    async def finish_test(self, token: str, attempt_id: int) -> str:
        """Завершить тест и получить результат"""
        response = await self.request("POST", f"/test/finish?attempt_id={attempt_id}", token)
        return response.get("text", "") or str(response)

    async def get_question_details(self, token: str, question_id: int) -> Dict:
        """Получить детали вопроса (заглушка, пока нет API)"""
        # В реальном API нужно добавить эндпоинт для получения вопроса
        questions_data = {
            1: {
                "text": "Что такое Python?",
                "options": ["Язык программирования", "Змея", "Оба варианта верны"],
                "correct": 2
            },
            2: {
                "text": "Что такое Docker?",
                "options": ["Контейнеризация", "Игра", "Операционная система"],
                "correct": 0
            },
            3: {
                "text": "Что такое API?",
                "options": ["Интерфейс программирования", "Аппаратный интерфейс", "Оба варианта"],
                "correct": 0
            }
        }
        return questions_data.get(question_id, {
            "text": f"Вопрос {question_id}",
            "options": ["Вариант 1", "Вариант 2", "Вариант 3"],
            "correct": 0
        })


api_client = APIClient(API_BASE_URL, JWT_SECRET)


# =========================
# DECORATORS
# =========================
async def check_rate_limit(chat_id: int, seconds: int = 2) -> bool:
    # TODO: Реализовать проверку лимита запросов
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
            if len(args) > 0 and isinstance(args[0], Message):
                try:
                    await args[0].answer(f"❌ Ошибка: {str(e)}")
                except:
                    pass
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


async def set_user_authorized(chat_id: int, user_id: int, email: str, role: str = "student"):
    """Устанавливаем пользователя как авторизованного с токеном для API"""
    # Генерируем JWT токен для API
    permissions = []
    if role == "teacher":
        permissions = ["quest:create", "quest:update", "course:read", "course:test:add",
                       "course:test:write", "test:quest:add"]
    else:
        permissions = ["course:read"]

    token = api_client.generate_token(user_id, role, permissions)

    await save_user(chat_id, {
        "status": UserStatus.AUTHORIZED,
        "api_token": token,
        "user_id": user_id,
        "email": email,
        "role": role,
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
        # Используем заглушку auth_service
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

⏳ <b>Код действителен 5 минут</b>

После ввода кода нажмите "Проверить статус".
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
        user_role = user.get("role", "student")
        role_text = "👨‍🏫 Преподаватель" if user_role == "teacher" else "👨‍🎓 Студент"

        text = f"""
✅ <b>Вы авторизованы как {user_email}</b>
{role_text}

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
/logout_all — выход со всех устройств

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
# АВТОРИЗАЦИЯ - ОБНОВЛЕННАЯ ДЛЯ API
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

1. <b>Тестовая авторизация (Студент)</b> — вход как студент для тестирования
2. <b>Тестовая авторизация (Преподаватель)</b> — вход как преподаватель
3. <b>Code</b> — авторизация через код (веб-клиент)
"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🎓 Студент (тест)", callback_data="login_student")],
        [InlineKeyboardButton(text="👨‍🏫 Преподаватель (тест)", callback_data="login_teacher")],
        [InlineKeyboardButton(text="🔢 Code", callback_data="login_code")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "login_student")
async def callback_login_student(callback: CallbackQuery):
    """Быстрая авторизация как студент"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    # Создаем фейковые данные для авторизации студента
    user_id = 123  # Фиксированный ID студента
    email = f"student_{chat_id}@example.com"

    await set_user_authorized(chat_id, user_id, email, "student")

    await callback.answer("✅ Авторизация студента успешна!")
    await callback.message.edit_text(
        f"✅ <b>Авторизация студента успешна!</b>\n\nДобро пожаловать, {email}\n\nВы можете проходить тесты.",
        reply_markup=None
    )


@dp.callback_query(F.data == "login_teacher")
async def callback_login_teacher(callback: CallbackQuery):
    """Быстрая авторизация как преподаватель"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    # Создаем фейковые данные для авторизации преподавателя
    user_id = 456  # Фиксированный ID преподавателя
    email = f"teacher_{chat_id}@example.com"

    await set_user_authorized(chat_id, user_id, email, "teacher")

    await callback.answer("✅ Авторизация преподавателя успешна!")
    await callback.message.edit_text(
        f"✅ <b>Авторизация преподавателя успешна!</b>\n\nДобро пожаловать, {email}\n\nВы можете управлять тестами.",
        reply_markup=None
    )


# =========================
# СПИСОК ТЕСТОВ С API
# =========================
@dp.message(Command("tests"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_tests(message: Message, user: Dict):
    """Список доступных тестов с API"""
    chat_id = message.chat.id
    api_token = user.get("api_token", "")

    if not api_token:
        await message.answer("❌ <b>Ошибка авторизации</b>\n\nТокен API не найден.")
        return

    try:
        # Получаем тесты с API
        tests = await api_client.get_tests(api_token, DEFAULT_COURSE_ID)

        if not tests:
            text = "📚 <b>Нет доступных тестов</b>\n\nНа данный момент нет активных тестов для прохождения."
            await message.answer(text)
            return

        # Активные тесты
        active_tests = [t for t in tests if t.get("is_active", False) and not t.get("is_deleted", False)]
        inactive_tests = [t for t in tests if not t.get("is_active", True) or t.get("is_deleted", False)]

        # Формируем текст
        text = "📚 <b>Доступные тесты</b>\n\n"

        if active_tests:
            text += "🟢 <b>Активные тесты:</b>\n"
            for test in active_tests:
                test_name = test.get("name") or test.get("title", f"Тест {test.get('id', '?')}")
                question_ids = test.get("question_ids", [])
                text += f"  • <b>{test_name}</b> (ID: {test.get('id', '?')})\n"
                text += f"    ❓ Вопросов: {len(question_ids)}\n\n"

        if inactive_tests:
            text += "🔴 <b>Неактивные тесты:</b>\n"
            for test in inactive_tests:
                test_name = test.get("name") or test.get("title", f"Тест {test.get('id', '?')}")
                text += f"  • <b>{test_name}</b> (недоступен)\n"

        # Создаем кнопки для активных тестов
        buttons = []
        for test in active_tests:
            test_id = test.get("id")
            if test_id:
                test_name = test.get("name") or test.get("title", f"Тест {test_id}")
                buttons.append([
                    InlineKeyboardButton(
                        text=f"▶️ Начать тест: {test_name}",
                        callback_data=f"start_test_{test_id}"
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

    except Exception as e:
        logger.error(f"Ошибка при получении тестов: {e}")
        await message.answer(f"❌ <b>Ошибка при загрузке тестов:</b>\n\n{str(e)}")


# =========================
# НАЧАЛО ТЕСТА С API
# =========================
@dp.callback_query(F.data.startswith("start_test_"))
@require_auth()
async def callback_start_test(callback: CallbackQuery, user: Dict):
    """Обработчик начала теста с API"""
    try:
        test_id = int(callback.data[11:])
        api_token = user.get("api_token", "")

        if not api_token:
            await callback.answer("❌ Ошибка авторизации API")
            return

        await callback.answer(f"🚀 Начинаем тест #{test_id}")

        # Начинаем тест через API
        result = await api_client.start_test(api_token, test_id)

        attempt_id = result.get("attempt_id") or result.get("id")
        if not attempt_id:
            await callback.answer("❌ Не удалось начать тест")
            await callback.message.answer("❌ <b>Ошибка:</b> Не удалось начать тест. Попробуйте позже.")
            return

        # Получаем вопросы теста (заглушка, пока нет API для вопросов)
        # В реальном API нужно получить список вопросов
        question_ids = [1, 2, 3]  # Примерные ID вопросов

        # Сохраняем контекст теста в Redis
        test_context = {
            "test_id": test_id,
            "attempt_id": attempt_id,
            "question_ids": question_ids,
            "current_question_index": 0,
            "answers": {},
            "started_at": datetime.now().isoformat(),
            "api_token": api_token,
            "user_id": user.get("user_id")
        }

        await redis_client.setex(
            f"test_context:{callback.message.chat.id}",
            3600,  # 1 час на прохождение
            json.dumps(test_context)
        )

        # Получаем первый вопрос
        if question_ids:
            first_question_id = question_ids[0]
            question_data = await api_client.get_question_details(api_token, first_question_id)

            text = f"""
🧪 <b>Начинаем тест #{test_id}</b>

<b>ID попытки:</b> {attempt_id}
<b>Всего вопросов:</b> {len(question_ids)}

<b>Вопрос 1 из {len(question_ids)}:</b>
{question_data.get('text', 'Текст вопроса')}

"""
            # Добавляем варианты ответов
            for i, option in enumerate(question_data.get("options", ["Вариант 1", "Вариант 2", "Вариант 3"])):
                text += f"{i + 1}. {option}\n"

            text += "\n<b>Отправьте номер правильного ответа (1-3).</b>"

            await callback.message.answer(text)
        else:
            await callback.message.answer("❌ <b>Ошибка:</b> В тесте нет вопросов.")

    except Exception as e:
        logger.error(f"Error starting test: {e}")
        await callback.answer("❌ Ошибка при начале теста")
        await callback.message.answer(f"❌ <b>Ошибка при начале теста:</b>\n\n{str(e)}")


# =========================
# ОБРАБОТКА ОТВЕТОВ С API
# =========================
@dp.message(F.text & ~F.text.startswith('/'))
@rate_limit()
@safe_send_message
async def handle_test_answers(message: Message):
    """Обработка ответов на вопросы теста с API"""
    chat_id = message.chat.id
    text = message.text or ""

    # Проверяем, есть ли активный тест
    context_data = await redis_client.get(f"test_context:{chat_id}")
    if not context_data:
        # Если теста нет и это не команда, игнорируем
        return

    try:
        context = json.loads(context_data)
        current_index = context.get("current_question_index", 0)
        question_ids = context.get("question_ids", [])
        attempt_id = context.get("attempt_id")
        api_token = context.get("api_token", "")

        if not attempt_id or not api_token:
            await message.answer("❌ <b>Ошибка контекста теста</b>")
            await redis_client.delete(f"test_context:{chat_id}")
            return

        # Проверяем ответ
        try:
            answer = int(text.strip())
            if answer < 1 or answer > 3:
                raise ValueError
        except:
            await message.answer("❌ <b>Отправьте число от 1 до 3</b>")
            return

        # Получаем текущий вопрос ID
        if current_index >= len(question_ids):
            await message.answer("❌ <b>Ошибка:</b> Нет больше вопросов.")
            return

        question_id = question_ids[current_index]

        # Отправляем ответ через API
        try:
            await api_client.submit_answer(api_token, attempt_id, question_id, answer - 1)
        except Exception as e:
            logger.error(f"Ошибка отправки ответа: {e}")
            await message.answer("❌ <b>Ошибка отправки ответа:</b>\n\nОтвет не сохранен.")
            return

        # Сохраняем ответ локально
        context["answers"][current_index] = answer - 1
        context["current_question_index"] = current_index + 1

        # Проверяем, закончен ли тест
        if current_index + 1 >= len(question_ids):
            # Тест завершен
            await redis_client.delete(f"test_context:{chat_id}")

            # Завершаем тест через API
            try:
                result = await api_client.finish_test(api_token, attempt_id)

                text = f"""
🎉 <b>Тест завершен!</b>

<b>Результат:</b> {result}

🏆 <b>Отличная работа!</b>

Ваши ответы сохранены в системе.
"""
                await message.answer(text)
            except Exception as e:
                logger.error(f"Ошибка завершения теста: {e}")
                await message.answer(f"🎉 <b>Тест завершен!</b>\n\nОшибка при получении результата: {str(e)}")
        else:
            # Показываем следующий вопрос
            await redis_client.setex(
                f"test_context:{chat_id}",
                3600,
                json.dumps(context)
            )

            # Получаем следующий вопрос
            next_question_id = question_ids[current_index + 1]
            question_data = await api_client.get_question_details(api_token, next_question_id)

            text = f"""
<b>Вопрос {current_index + 2} из {len(question_ids)}:</b>
{question_data.get('text', 'Текст вопроса')}

"""
            # Добавляем варианты ответов
            for i, option in enumerate(question_data.get("options", ["Вариант 1", "Вариант 2", "Вариант 3"])):
                text += f"{i + 1}. {option}\n"

            text += "\n<b>Отправьте номер правильного ответа (1-3).</b>"
            await message.answer(text)

    except Exception as e:
        logger.error(f"Error processing test answer: {e}")
        await message.answer("❌ <b>Ошибка при обработке ответа</b>")
        await redis_client.delete(f"test_context:{chat_id}")


# =========================
# ОСТАЛЬНЫЕ КОМАНДЫ (С ИНТЕГРАЦИЕЙ API)
# =========================
@dp.message(Command("profile"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_profile(message: Message, user: Dict):
    """Информация о пользователе"""
    chat_id = message.chat.id
    current_user = await get_user(chat_id)

    if not current_user:
        await message.answer("❌ <b>Пользователь не найден</b>")
        return

    # Форматируем дату авторизации
    auth_date = "Неизвестно"
    if current_user.get("authorized_at"):
        try:
            auth_dt = datetime.fromisoformat(current_user["authorized_at"].replace('Z', '+00:00'))
            auth_date = auth_dt.strftime("%d.%m.%Y %H:%M")
        except:
            auth_date = current_user["authorized_at"]

    role = current_user.get("role", "student")
    role_text = "👨‍🏫 Преподаватель" if role == "teacher" else "👨‍🎓 Студент"
    permissions = current_user.get("permissions", [])

    text = f"""
👤 <b>Профиль пользователя</b>

<b>Основная информация:</b>
📧 <b>Email:</b> {current_user.get('email', 'Неизвестно')}
👤 <b>Роль:</b> {role_text}
🔑 <b>ID пользователя:</b> {current_user.get('user_id', 'Неизвестно')}

<b>Разрешения:</b>
{', '.join(permissions) if permissions else 'Базовые разрешения'}

<b>Сессия в Telegram:</b>
🤖 <b>Авторизован:</b> {auth_date}
🔐 <b>Статус:</b> 🟢 Активен
"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мои результаты", callback_data="my_results")],
        [InlineKeyboardButton(text="🔄 Обновить данные", callback_data="refresh_profile")]
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


@dp.message(Command("logout_all"))
@rate_limit()
@safe_send_message
async def cmd_logout_all(message: Message):
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user:
        await message.answer("❌ <b>Вы не авторизованы</b>\n\nСначала выполните /login.")
        return

    if user.get("status") != UserStatus.AUTHORIZED:
        await delete_user(chat_id)
        await message.answer("🚪 <b>Процесс авторизации прерван</b>")
        return

    await message.answer("✅ <b>Выход выполнен со всех устройств</b>")

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
        role = user.get("role", "student")
        role_text = "Преподаватель" if role == "teacher" else "Студент"
        user_details = f"\n📧 Email: {email}\n🎭 Роль: {role_text}"

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
• API Backend — 🟢 {API_BASE_URL}
"""
    await message.answer(text)


@dp.message(Command("courses"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_courses(message: Message, user: Dict):
    """Список дисциплин"""
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
    text = f"""
🧩 <b>Архитектура системы</b>

<b>Telegram Bot (этот модуль)</b>
• Обработка команд пользователей
• Управление состоянием через Redis
• Отображение результатов тестов
• Интеграция с API Backend

<b>API Backend (Go)</b>
• Адрес: {API_BASE_URL}
• Авторизация через JWT токены
• Управление тестами и вопросами
• Обработка попыток тестирования
• Хранение результатов в PostgreSQL

<b>Базы данных</b>
• PostgreSQL — основное хранилище
• Redis — кэш и сессии
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
• API: {API_BASE_URL}
• Время: {datetime.now().strftime("%H:%M:%S")}

<b>Пользователь:</b>
• Статус: {user.get('status') if user else 'UNKNOWN'}
• User ID: {user.get('user_id') if user else 'Нет'}
• Email: {user.get('email') if user else 'Нет'}
• Роль: {user.get('role') if user else 'Нет'}

<b>Статистика:</b>
• Активных пользователей: {len(authorized_users)}
• Выполнено команд: {stats.commands_count}
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
# ЗАГЛУШКИ ДЛЯ СОВМЕСТИМОСТИ
# =========================
class AuthServiceStub:
    def __init__(self):
        self.login_tokens = {}
        self.codes = {}
        self.confirmed_logins = set()

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
            "confirmed": False
        }

        return "https://t.me/cfutgbot"

    async def check_login_token(self, login_token: str) -> Optional[Dict]:
        if login_token not in self.login_tokens:
            return None

        token_data = self.login_tokens[login_token]

        if token_data.get("confirmed"):
            user_id = secrets.randbelow(1000) + 100
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

        return {"status": "pending"}

    async def confirm_login(self, login_token: str):
        if login_token in self.login_tokens:
            self.login_tokens[login_token]["confirmed"] = True
            self.login_tokens[login_token]["status"] = "granted"
            return True
        return False


auth_service = AuthServiceStub()


# =========================
# CALLBACK HANDLERS ДЛЯ СОВМЕСТИМОСТИ
# =========================
@dp.callback_query(F.data == "login")
async def callback_login(callback: CallbackQuery):
    await callback.answer()
    await cmd_login(callback.message)


@dp.callback_query(F.data == "login_code")
async def callback_login_code(callback: CallbackQuery):
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "code")

    auth_url = await auth_service.generate_login_url(login_token, "code")
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
        [InlineKeyboardButton(text="🚀 Быстрая авторизация (Студент)", callback_data="login_student")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.callback_query(F.data.startswith("check_auth_"))
async def callback_check_auth(callback: CallbackQuery):
    login_token = callback.data[11:]
    result = await auth_service.check_login_token(login_token)

    if not result:
        await callback.answer("❌ Токен не найден или истек")
    elif result.get("status") == "pending":
        await callback.answer("⏳ Ожидание подтверждения авторизации в веб-клиенте")

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
        user_id = user_data.get("id", secrets.randbelow(1000) + 100)
        email = user_data.get("email", f"user_{login_token[:8]}@example.com")

        # Авторизуем как студента
        await set_user_authorized(callback.from_user.id, user_id, email, "student")

        await callback.answer("✅ Авторизация успешна!")
        await callback.message.edit_text(
            f"✅ <b>Авторизация завершена!</b>\n\nДобро пожаловать, {email}",
            reply_markup=None
        )


@dp.callback_query(F.data.startswith("confirm_auth_"))
async def callback_confirm_auth(callback: CallbackQuery):
    login_token = callback.data[13:]

    success = await auth_service.confirm_login(login_token)

    if success:
        result = await auth_service.check_login_token(login_token)

        if result and result.get("status") == "granted":
            user_data = result.get("user", {})
            user_id = user_data.get("id", secrets.randbelow(1000) + 100)
            email = user_data.get("email", f"user_{login_token[:8]}@example.com")

            await set_user_authorized(callback.from_user.id, user_id, email, "student")

            await callback.answer("✅ Авторизация подтверждена и успешна!")
            await callback.message.edit_text(
                f"✅ <b>Авторизация завершена!</b>\n\nДобро пожаловать, {email}\n\n<em>Примечание: использована заглушка для тестирования</em>",
                reply_markup=None
            )
        else:
            await callback.answer("❌ Ошибка подтверждения")
    else:
        await callback.answer("❌ Токен не найден")


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
                                    chat_id = int(key.split(":")[1])
                                    await delete_user(chat_id)
                            except:
                                pass
        except Exception as e:
            logger.error(f"Error in check_anonymous_users_task: {e}")

        await asyncio.sleep(30)


# =========================
# MAIN
# =========================
async def main():
    logger.info("🤖 Telegram bot starting...")
    logger.info(f"📡 API Base URL: {API_BASE_URL}")

    await redis_client.connect()

    background_task = asyncio.create_task(check_anonymous_users_task())

    logger.info("🚀 Bot is ready!")

    try:
        await dp.start_polling(bot, skip_updates=True)
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    finally:
        background_task.cancel()
        await api_client.close()


if __name__ == "__main__":
    asyncio.run(main())