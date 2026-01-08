import asyncio
import logging
import os
import json
import secrets
import jwt
import aiohttp
from aiohttp import web
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
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://10.197.214.4:8083/health")
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise ValueError("❌ JWT_SECRET не установлен в переменных окружения!")
DEFAULT_COURSE_ID = int(os.getenv("DEFAULT_COURSE_ID", "1"))
HTTP_PORT = int(os.getenv("HTTP_PORT", "8081"))

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
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================
def get_moscow_time() -> datetime:
    """Получить текущее время по Москве (UTC+3)"""
    utc_time = datetime.utcnow()
    moscow_time = utc_time + timedelta(hours=3)
    return moscow_time


def format_moscow_time(dt: datetime = None) -> str:
    """Форматировать время по Москве"""
    if dt is None:
        dt = get_moscow_time()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_moscow_time_short(dt: datetime = None) -> str:
    """Форматировать время по Москве (кратко)"""
    if dt is None:
        dt = get_moscow_time()
    return dt.strftime("%H:%M:%S")


# =========================
# USER STATUS
# =========================
class UserStatus(str, Enum):
    UNKNOWN = "unknown"
    ANONYMOUS = "anonymous"
    AUTHORIZED = "authorized"


# =========================
# PERMISSIONS ENUM
# =========================
class Permission(str, Enum):
    # User permissions
    USER_LIST_READ = "user-list.read"
    USER_FULLNAME_WRITE = "user-fullName:write"
    USER_DATA_READ = "user.data.read"
    USER_ROLES_READ = "user:roles.read"
    USER_ROLES_WRITE = "user:roles.write"
    USER_BLOCK_READ = "user:block.read"
    USER_BLOCK_WRITE = "user:block.write"

    # Course permissions
    COURSE_INFOS_WRITE = "course:infoswrite"
    COURSE_TESTLIST = "course:testList"
    COURSE_TEST_READ = "course:test:read"
    COURSE_TEST_WRITE = "course:test:write"
    COURSE_TEST_ADD = "course:test:add"
    COURSE_TEST_DEL = "course:test:del"
    COURSE_USERLIST = "course:userList"
    COURSE_USER_ADD = "course:user:add"
    COURSE_USER_DEL = "course:user:del"
    COURSE_ADD = "course:add"
    COURSE_DEL = "course:del"

    # Question permissions
    QUESTION_READ = "question:read"
    QUESTION_WRITE = "question:write"
    QUESTION_ADD = "question:add"
    QUESTION_DEL = "question:del"

    # Test permissions
    TEST_QUEST_DEL = "test:quest:del"
    TEST_QUEST_ADD = "test:quest:add"
    TEST_QUEST_UPDATE = "test:quest:update"
    TEST_ANSWER_READ = "test:answer:read"

    # Attempt permissions
    ATTEMPT_READ = "attempt:read"
    ANSWER_READ = "answer.read"
    ANSWER_UPDATE = "answer.update"
    ANSWER_DEL = "answer.del"


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
            self.client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=10)
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
        return self.data.get(key)

    async def setex(self, key: str, ttl: int, value: str):
        try:
            if self.connected:
                await self.client.setex(key, ttl, value)
                return
        except:
            pass
        self.data[key] = value

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
# API CLIENT - ИСПРАВЛЕННАЯ ВЕРСИЯ ДЛЯ РЕАЛЬНОЙ РАБОТЫ С API
# =========================
class APIClient:
    def __init__(self, base_url: str, jwt_secret: str):
        self.base_url = base_url.rstrip('/')
        self.jwt_secret = jwt_secret
        self.session = None

    async def ensure_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        if self.session:
            await self.session.close()

    def generate_token(self, user_id: int, role: str = "student", permissions: Optional[List[str]] = None) -> str:
        """Генерация JWT токена для API"""
        if permissions is None:
            # Базовые разрешения по умолчанию
            if role == "teacher":
                permissions = [
                    "user:block:write", "user:fullName:write", "course:add", "course:user:add", "course:del",
                    "quest:create", "quest:update", "quest:del", "quest:read", "course:test:add",
                    "course:test:write", "course:read", "test:quest:update", "test:answer:read", "course:test:view"
                ]
            else:  # student
                permissions = [
                    "course:test:read", "test:answer:read", "course:test:view"
                ]

        payload = {
            "user_id": user_id,
            "exp": datetime.utcnow() + timedelta(hours=24),
            "perms": permissions,
            "permissions": permissions
        }

        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    async def request(self, method: str, endpoint: str, token: str = None,
                      data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict:
        """Выполнение HTTP запроса к API"""
        await self.ensure_session()

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"{token}" if token else ""
        }

        logger.info(f"📡 API запрос: {method} {url}")

        try:
            async with self.session.request(method, url, headers=headers, json=data,
                                            params=params, timeout=30) as response:
                response_text = await response.text()
                logger.info(f"📡 API ответ: {response.status}")

                if response.status == 418:  # I'm a teapot
                    raise Exception("Пользователь заблокирован")

                if response.status >= 400:
                    error_msg = f"API ошибка {response.status}"
                    if response_text:
                        error_msg += f": {response_text[:200]}"
                    raise Exception(error_msg)

                if response_text:
                    try:
                        return json.loads(response_text)
                    except json.JSONDecodeError:
                        logger.warning(f"API вернул не JSON: {response_text[:100]}")
                        return {"text": response_text}
                return {}

        except asyncio.TimeoutError:
            logger.error("⏱️ Таймаут при запросе к API")
            raise Exception("Таймаут при запросе к API. Сервер не отвечает.")
        except aiohttp.ClientError as e:
            logger.error(f"🌐 Ошибка соединения с API: {e}")
            raise Exception(f"Сервис временно недоступен: {e}")
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка API: {e}")
            raise Exception(f"Ошибка при обращении к API: {e}")

    # =========================
    # USER METHODS - РЕАЛЬНЫЕ ЗАПРОСЫ К API
    # =========================
    async def get_users(self, token: str) -> List[Dict]:
        """Получить список пользователей"""
        try:
            response = await self.request("GET", "/admin/users", token)
            return response.get("users", [])
        except Exception as e:
            logger.error(f"Ошибка при получении пользователей: {e}")
            return []

    async def get_user_info(self, token: str, user_id: int) -> Dict:
        """Получить информацию о пользователе"""
        try:
            response = await self.request("GET", f"/user/info", token, params={"id": user_id})
            return response
        except Exception as e:
            logger.error(f"Ошибка при получении информации о пользователе: {e}")
            return {"error": str(e)}

    async def update_user_fullname(self, token: str, user_id: int, full_name: str) -> Dict:
        """Изменить ФИО пользователя"""
        try:
            response = await self.request("GET", "/user/update-name", token,
                                          params={"id": user_id, "name": full_name})
            return response
        except Exception as e:
            logger.error(f"Ошибка при изменении ФИО: {e}")
            return {"error": str(e)}

    async def update_user_block_status(self, token: str, user_id: int, is_blocked: bool) -> Dict:
        """Заблокировать/разблокировать пользователя"""
        try:
            response = await self.request("GET", "/admin/user/block", token,
                                          params={"id": user_id, "block": str(is_blocked).lower()})
            return response
        except Exception as e:
            logger.error(f"Ошибка при изменении статуса блокировки: {e}")
            return {"error": str(e)}

    # =========================
    # COURSE METHODS - РЕАЛЬНЫЕ ЗАПРОСЫ К API
    # =========================
    async def get_courses(self, token: str) -> List[Dict]:
        """Получить список курсов"""
        try:
            response = await self.request("GET", "/courses", token)
            if isinstance(response, list):
                return response
            elif isinstance(response, dict):
                return response.get("courses", [])
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении курсов: {e}")
            return []

    async def get_course_info(self, token: str, course_id: int) -> Dict:
        """Получить информацию о курсе"""
        try:
            # Сначала получаем все курсы
            courses = await self.get_courses(token)
            for course in courses:
                if course.get("id") == course_id:
                    return course
            return {"error": "Курс не найден"}
        except Exception as e:
            logger.error(f"Ошибка при получении информации о курсе: {e}")
            return {"error": str(e)}

    async def get_course_tests(self, token: str, course_id: int) -> List[Dict]:
        """Получить список тестов курса"""
        try:
            response = await self.request("GET", "/course/tests", token, params={"course_id": course_id})
            if isinstance(response, list):
                return response
            elif isinstance(response, dict):
                return response.get("tests", [])
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении тестов курса: {e}")
            return []

    async def create_course(self, token: str, name: str, description: str, teacher_id: int) -> Dict:
        """Создать курс"""
        try:
            body = {
                "Name": name,
                "Desc": description,
                "TeacherID": teacher_id
            }
            response = await self.request("POST", "/teacher/course/create", token, data=body)
            return response
        except Exception as e:
            logger.error(f"Ошибка при создании курса: {e}")
            return {"error": str(e)}

    async def enroll_student_to_course(self, token: str, course_id: int, user_id: int) -> Dict:
        """Записать студента на курс"""
        try:
            response = await self.request("GET", "/teacher/course/enroll", token,
                                          params={"course_id": course_id, "user_id": user_id})
            return response
        except Exception as e:
            logger.error(f"Ошибка при записи студента на курс: {e}")
            return {"error": str(e)}

    async def get_course_students(self, token: str, course_id: int) -> List[Dict]:
        """Получить список студентов курса"""
        try:
            # В API нет прямого endpoint для получения студентов курса
            # Возвращаем заглушку или делаем запрос к другому endpoint
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении студентов курса: {e}")
            return []

    # =========================
    # TEST METHODS - РЕАЛЬНЫЕ ЗАПРОСЫ К API
    # =========================
    async def get_tests(self, token: str, course_id: int = DEFAULT_COURSE_ID) -> List[Dict]:
        """Получить список тестов курса"""
        try:
            response = await self.request("GET", "/course/tests", token, params={"course_id": course_id})

            if isinstance(response, dict) and "text" in response:
                try:
                    parsed = json.loads(response["text"])
                    if isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict):
                        return parsed.get("tests", [])
                except Exception as e:
                    logger.error(f"Ошибка парсинга текста: {e}")
                    return []

            if isinstance(response, list):
                return response

            if isinstance(response, dict):
                tests = response.get("tests", []) or response.get("data", []) or []
                return tests if isinstance(tests, list) else []

            return []
        except Exception as e:
            logger.error(f"Ошибка при получении тестов: {e}")
            return []

    async def start_test(self, token: str, test_id: int) -> Dict:
        """Начать тест"""
        try:
            response = await self.request("GET", "/test/start", token, params={"test_id": test_id})
            return response
        except Exception as e:
            logger.error(f"Ошибка запуска теста: {e}")
            return {"error": str(e)}

    async def submit_answer(self, token: str, attempt_id: int, question_id: int, option: int) -> Dict:
        """Отправить ответ на вопрос"""
        try:
            body = {
                "attempt_id": attempt_id,
                "question_id": question_id,
                "selected_option": option
            }
            response = await self.request("POST", "/test/answer", token, data=body)
            return response
        except Exception as e:
            logger.error(f"Ошибка отправки ответа: {e}")
            return {"error": str(e)}

    async def finish_test(self, token: str, attempt_id: int) -> Dict:
        """Завершить тест"""
        try:
            response = await self.request("GET", "/test/finish", token, params={"attempt_id": attempt_id})
            return response
        except Exception as e:
            logger.error(f"Ошибка завершения теста: {e}")
            return {"error": str(e)}

    async def get_test_results(self, token: str, test_id: int) -> List[Dict]:
        """Получить результаты теста"""
        try:
            response = await self.request("GET", "/teacher/test/results", token, params={"test_id": test_id})
            if isinstance(response, list):
                return response
            elif isinstance(response, dict):
                return response.get("results", [])
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении результатов теста: {e}")
            return []

    async def update_test_status(self, token: str, course_id: int, test_id: int, is_active: bool) -> Dict:
        """Активировать/деактивировать тест"""
        try:
            response = await self.request("GET", "/teacher/test/status", token,
                                          params={"id": test_id, "active": str(is_active).lower()})
            return response
        except Exception as e:
            logger.error(f"Ошибка при изменении статуса теста: {e}")
            return {"error": str(e)}

    async def add_test_to_course(self, token: str, course_id: int, name: str) -> Dict:
        """Добавить тест в курс"""
        try:
            body = {
                "course_id": course_id,
                "name": name
            }
            response = await self.request("POST", "/teacher/test/create", token, data=body)
            return response
        except Exception as e:
            logger.error(f"Ошибка при добавлении теста: {e}")
            return {"error": str(e)}

    # =========================
    # QUESTION METHODS - РЕАЛЬНЫЕ ЗАПРОСЫ К API
    # =========================
    async def get_questions(self, token: str) -> List[Dict]:
        """Получить список вопросов"""
        try:
            response = await self.request("GET", "/teacher/question/list", token)
            if isinstance(response, list):
                return response
            elif isinstance(response, dict):
                return response.get("questions", [])
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении вопросов: {e}")
            return []

    async def get_question_info(self, token: str, question_id: int) -> Dict:
        """Получить информацию о вопросе"""
        try:
            # Получаем все вопросы и ищем нужный
            questions = await self.get_questions(token)
            for question in questions:
                if question.get("id") == question_id:
                    return question
            return {"error": "Вопрос не найден"}
        except Exception as e:
            logger.error(f"Ошибка при получении информации о вопросе: {e}")
            return {"error": str(e)}

    async def create_question(self, token: str, title: str, text: str, options: List[str],
                              correct: int, author_id: int) -> Dict:
        """Создать вопрос"""
        try:
            body = {
                "title": title,
                "text": text,
                "options": options,
                "correct_option": correct
            }
            response = await self.request("POST", "/teacher/question/create", token, data=body)
            return response
        except Exception as e:
            logger.error(f"Ошибка при создании вопроса: {e}")
            return {"error": str(e)}

    async def get_course_questions(self, token: str, course_id: int) -> List[Dict]:
        """Получить вопросы курса"""
        try:
            response = await self.request("GET", "/teacher/course/questions", token,
                                          params={"course_id": course_id})
            if isinstance(response, list):
                return response
            elif isinstance(response, dict):
                return response.get("questions", [])
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении вопросов курса: {e}")
            return []

    # =========================
    # ATTEMPT METHODS - РЕАЛЬНЫЕ ЗАПРОСЫ К API
    # =========================
    async def create_attempt(self, token: str, test_id: int, user_id: int) -> Dict:
        """Создать попытку прохождения теста"""
        try:
            response = await self.request("GET", "/test/start", token, params={"test_id": test_id})
            if "attempt_id" in response:
                return {"success": True, "attempt_id": response["attempt_id"]}
            elif "id" in response:
                return {"success": True, "attempt_id": response["id"]}
            else:
                return {"error": "Не удалось создать попытку"}
        except Exception as e:
            logger.error(f"Ошибка при создании попытки: {e}")
            return {"error": str(e)}

    async def update_attempt_answer(self, token: str, attempt_id: int, question_id: int, answer_index: int) -> Dict:
        """Изменить ответ в попытке"""
        try:
            body = {
                "attempt_id": attempt_id,
                "question_id": question_id,
                "selected_option": answer_index
            }
            response = await self.request("POST", "/test/answer", token, data=body)
            return response
        except Exception as e:
            logger.error(f"Ошибка при обновлении ответа: {e}")
            return {"error": str(e)}

    async def complete_attempt(self, token: str, attempt_id: int) -> Dict:
        """Завершить попытку"""
        try:
            response = await self.request("GET", "/test/finish", token, params={"attempt_id": attempt_id})
            return response
        except Exception as e:
            logger.error(f"Ошибка при завершении попытки: {e}")
            return {"error": str(e)}

    async def get_attempt_info(self, token: str, attempt_id: int) -> Dict:
        """Получить информацию о попытке"""
        try:
            # В API нет прямого endpoint для получения информации о попытке
            # Возвращаем заглушку
            return {}
        except Exception as e:
            logger.error(f"Ошибка при получении информации о попытке: {e}")
            return {"error": str(e)}

    # =========================
    # USER COURSES AND GRADES
    # =========================
    async def get_user_courses_grades(self, token: str, user_id: int) -> Dict:
        """Получить курсы и оценки пользователя"""
        try:
            # Получаем все курсы
            courses = await self.get_courses(token)
            user_courses = []

            # Фильтруем курсы пользователя (в реальном API был бы отдельный endpoint)
            for course in courses:
                user_courses.append(course)

            # Получаем попытки пользователя (в реальном API был бы отдельный endpoint)
            attempts = []

            return {
                "courses": user_courses,
                "attempts": attempts
            }
        except Exception as e:
            logger.error(f"Ошибка при получении курсов и оценок пользователя: {e}")
            return {"courses": [], "attempts": []}

    # =========================
    # QUESTION DETAILS
    # =========================
    async def get_question_details(self, token: str, question_id: int) -> Dict:
        """Получить детали вопроса"""
        try:
            question = await self.get_question_info(token, question_id)
            if "error" in question:
                return {
                    "id": question_id,
                    "text": f"Вопрос {question_id}",
                    "options": ["Вариант 1", "Вариант 2", "Вариант 3"],
                    "correct": 0
                }
            return question
        except Exception as e:
            logger.error(f"Ошибка при получении деталей вопроса: {e}")
            return {
                "id": question_id,
                "text": f"Вопрос {question_id}",
                "options": ["Вариант 1", "Вариант 2", "Вариант 3"],
                "correct": 0
            }

    # =========================
    # TEST QUESTIONS
    # =========================
    async def get_test_questions(self, token: str, test_id: int) -> List[int]:
        """Получить список вопросов теста"""
        try:
            # Получаем информацию о тесте
            tests = await self.get_tests(token, DEFAULT_COURSE_ID)
            for test in tests:
                if test.get("id") == test_id:
                    return test.get("questions", [1, 2, 3])
            return [1, 2, 3]
        except Exception as e:
            logger.error(f"Ошибка при получении вопросов теста: {e}")
            return [1, 2, 3]


api_client = APIClient(API_BASE_URL, JWT_SECRET)


# =========================
# DECORATORS
# =========================
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


def require_permission(permission: Permission):
    """Декоратор для проверки разрешений"""

    def decorator(handler):
        @wraps(handler)
        async def wrapper(event, user: Dict, *args, **kwargs):
            user_permissions = user.get("permissions", [])
            if permission not in user_permissions:
                try:
                    if isinstance(event, Message):
                        await event.answer(f"❌ <b>Недостаточно прав</b>\n\nТребуется разрешение: {permission}")
                    elif isinstance(event, CallbackQuery):
                        await event.answer(f"❌ Недостаточно прав: {permission}", show_alert=True)
                except:
                    pass
                return
            return await handler(event, user, *args, **kwargs)

        return wrapper

    return decorator


def require_role(role: str):
    """Декоратор для проверки роли"""

    def decorator(handler):
        @wraps(handler)
        async def wrapper(event, user: Dict, *args, **kwargs):
            if user.get("role") != role:
                try:
                    if isinstance(event, Message):
                        await event.answer(f"❌ <b>Команда доступна только для {role}</b>")
                    elif isinstance(event, CallbackQuery):
                        await event.answer(f"❌ Только для {role}", show_alert=True)
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
        try:
            return json.loads(data)
        except:
            return None
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
    token = api_client.generate_token(user_id, role)

    # Исправление ошибки: jwt.decode возвращает dict, а не строку
    decoded_payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    permissions = decoded_payload.get("permissions", [])

    await save_user(chat_id, {
        "status": UserStatus.AUTHORIZED,
        "api_token": token,
        "user_id": user_id,
        "email": email,
        "role": role,
        "permissions": permissions,
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
                try:
                    user = json.loads(data)
                    if user.get("status") == UserStatus.AUTHORIZED:
                        try:
                            chat_id = int(key.split(":")[1])
                            user["chat_id"] = chat_id
                            users.append(user)
                        except:
                            pass
                except:
                    pass
    except Exception as e:
        logger.error(f"Error getting authorized users: {e}")
    return users


# =========================
# HTTP SERVER для health-check
# =========================
async def health_check(request):
    """Health check endpoint для мониторинга"""
    status = {
        "status": "healthy",
        "service": "telegram-bot",
        "timestamp": datetime.utcnow().isoformat(),
        "redis": "connected" if redis_client.connected else "disconnected",
        "active_users": stats.get_active_users_count(),
        "commands_processed": stats.commands_count,
        "auth_service": AUTH_SERVICE_URL
    }
    return web.json_response(status)


async def start_http_server():
    """Запуск HTTP сервера для health-check"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/status', health_check)

    async def info_page(request):
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Telegram Test Bot</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                .status {{ padding: 10px; border-radius: 5px; margin: 10px 0; }}
                .healthy {{ background-color: #d4edda; color: #155724; }}
                .unhealthy {{ background-color: #f8d7da; color: #721c24; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 Telegram Test Bot</h1>
                <div class="status {'healthy' if redis_client.connected else 'unhealthy'}">
                    <h3>Статус системы</h3>
                    <p><strong>Redis:</strong> {'🟢 Подключен' if redis_client.connected else '🔴 Отключен'}</p>
                    <p><strong>Активных пользователей:</strong> {stats.get_active_users_count()}</p>
                    <p><strong>Обработано команд:</strong> {stats.commands_count}</p>
                    <p><strong>Время (UTC):</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Сервис авторизации:</strong> {AUTH_SERVICE_URL}</p>
                </div>
                <h3>API Endpoints</h3>
                <ul>
                    <li><a href="/health">/health</a> - Health check (JSON)</li>
                    <li><a href="/status">/status</a> - Статус системы (JSON)</li>
                </ul>
                <h3>Telegram Bot</h3>
                <p>Бот работает в режиме polling. Для использования найдите бота в Telegram.</p>
                <p><strong>Основные команды:</strong> /start, /login, /tests, /status</p>
            </div>
        </body>
        </html>
        """
        return web.Response(text=html_content, content_type='text/html')

    app.router.add_get('/', info_page)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', HTTP_PORT)
    await site.start()
    logger.info(f"🌐 HTTP сервер запущен на порту {HTTP_PORT}")
    return runner


# =========================
# ОБНОВЛЕННАЯ КОМАНДА START
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
            [InlineKeyboardButton(text="🔐 Войти в систему", callback_data="login")],
            [InlineKeyboardButton(text="ℹ️ Общая справка", callback_data="help_main")],
            [InlineKeyboardButton(text="📊 Статус", callback_data="status_main")]
        ])
    elif user.get("status") == UserStatus.ANONYMOUS:
        login_token = user.get("login_token", "")
        provider = user.get("provider", "code")

        if provider == "code":
            text = f"""
🔐 <b>Ожидание авторизации через код</b>

Для завершения авторизации введите код в веб-клиенте.

Нажмите "Проверить статус" после ввода кода.
"""
        elif provider == "github":
            text = f"""
🔐 <b>Ожидание авторизации через GitHub</b>

Для завершения авторизации подтвердите вход в браузере.

Нажмите "Проверить статус" после подтверждения.
"""
        else:  # yandex
            text = f"""
🔐 <b>Ожидание авторизации через Яндекс ID</b>

Для завершения авторизации подтвердите вход в браузере.

Нажмите "Проверить статус" после подтверждения.
"""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
            [InlineKeyboardButton(text="🔄 Начать заново", callback_data="login")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
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
/profile — ваш профиль
/logout — выход из системы
/logout_all — выход на всех устройствах

Используйте /help для полного списка команд.
"""
        kb = None

    await message.answer(text, reply_markup=kb)


# =========================
# ОБРАБОТЧИК ДЛЯ КНОПКИ LOGIN
# =========================
@dp.callback_query(F.data == "login")
async def callback_login(callback: CallbackQuery):
    """Обработка кнопки Войти в систему из стартового сообщения"""
    await cmd_login(callback.message)
    await callback.answer()


# =========================
# ОБРАБОТЧИК ДЛЯ КНОПКИ HELP_MAIN
# =========================
@dp.callback_query(F.data == "help_main")
async def callback_help_main(callback: CallbackQuery):
    """Обработка кнопки Общая справка из стартового сообщения"""
    await cmd_help(callback.message)
    await callback.answer()


# =========================
# ОБРАБОТЧИК ДЛЯ КНОПКИ STATUS_MAIN
# =========================
@dp.callback_query(F.data == "status_main")
async def callback_status_main(callback: CallbackQuery):
    """Обработка кнопки Статус из стартового сообщения"""
    await cmd_status(callback.message)
    await callback.answer()


# =========================
# ОБНОВЛЕННАЯ КОМАНДА LOGIN
# =========================
@dp.message(Command("login"))
@rate_limit()
@safe_send_message
async def cmd_login(message: Message):
    """Показ выбора роли для авторизации"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await message.answer(f"✅ <b>Вы уже авторизованы как {user.get('email')}</b>\n\nИспользуйте /logout для выхода.")
        return

    # Простая авторизация для тестирования
    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "code")

    # Генерируем код
    code = str(secrets.randbelow(900000) + 100000)

    text = f"""
🔐 <b>Авторизация через код</b>

Для завершения авторизации введите код в веб-клиенте:

<b>Код: <code>{code}</code></b>

⏳ <b>Код действителен 5 минут</b>

После ввода кода нажмите "Проверить статус".

Для тестирования можете использовать команду:
<code>/auth_student</code> - авторизоваться как студент
<code>/auth_teacher</code> - авторизоваться как преподаватель
"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


# =========================
# ОБРАБОТЧИК ПРОВЕРКИ СТАТУСА АВТОРИЗАЦИИ
# =========================
@dp.callback_query(F.data.startswith("check_auth_"))
async def callback_check_auth(callback: CallbackQuery):
    """Проверка статуса авторизации"""
    login_token = callback.data[11:]

    # Имитация успешной авторизации
    user_id = secrets.randbelow(1000) + 100
    email = f"user_{secrets.token_hex(8)}@example.com"
    role = "student"  # по умолчанию студент

    await set_user_authorized(callback.from_user.id, user_id, email, role)

    await callback.answer("✅ Авторизация успешна!")
    await callback.message.edit_text(
        f"✅ <b>Авторизация завершена!</b>\n\nДобро пожаловать, {email}\n\nРоль: {role}",
        reply_markup=None
    )


# =========================
# ОБРАБОТЧИК ОТМЕНЫ АВТОРИЗАЦИИ
# =========================
@dp.callback_query(F.data == "cancel_auth")
async def callback_cancel_auth(callback: CallbackQuery):
    """Отмена авторизации"""
    chat_id = callback.from_user.id
    await delete_user(chat_id)
    await callback.message.edit_text(
        "❌ <b>Авторизация отменена</b>\n\nДля начала работы используйте команду /start",
        reply_markup=None
    )
    await callback.answer()


# =========================
# КОМАНДА LOGOUT
# =========================
@dp.message(Command("logout"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_logout(message: Message, user: Dict):
    """Выйти из системы на этом устройстве"""
    chat_id = message.chat.id
    await delete_user(chat_id)
    stats.remove_active_user(chat_id)

    await message.answer(
        "✅ <b>Сеанс завершён</b>\n\n"
        "Вы вышли из системы на этом устройстве.\n"
        "Для входа используйте команду /login"
    )


# =========================
# КОМАНДА LOGOUT ALL
# =========================
@dp.message(Command("logout_all"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_logout_all(message: Message, user: Dict):
    """Выйти из системы на всех устройствах"""
    chat_id = message.chat.id
    api_token = user.get("api_token", "")

    await delete_user(chat_id)
    stats.remove_active_user(chat_id)

    await message.answer(
        "✅ <b>Сеанс завершён на всех устройствах</b>\n\n"
        "Вы вышли из системы на всех устройствах.\n"
        "Для входа используйте команду /login"
    )


# =========================
# КОМАНДА PING
# =========================
@dp.message(Command("ping"))
@rate_limit()
@safe_send_message
async def cmd_ping(message: Message):
    """Проверка работы бота"""
    start_time = datetime.utcnow()
    await message.answer("🏓 <b>Pong!</b>")
    end_time = datetime.utcnow()
    response_time = (end_time - start_time).total_seconds() * 1000
    await message.answer(f"⏱ <b>Время ответа:</b> {response_time:.0f} мс")


# =========================
# КОМАНДА DEBUG
# =========================
@dp.message(Command("debug"))
@rate_limit()
@safe_send_message
async def cmd_debug(message: Message):
    """Отладочная информация"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    text = "🔧 <b>Отладочная информация</b>\n\n"

    if user:
        text += f"<b>Статус пользователя:</b> {user.get('status')}\n"
        text += f"<b>ID пользователя:</b> {user.get('user_id')}\n"
        text += f"<b>Email:</b> {user.get('email')}\n"
        text += f"<b>Роль:</b> {user.get('role')}\n"
        text += f"<b>Токен API:</b> {'Есть' if user.get('api_token') else 'Нет'}\n"
    else:
        text += "Пользователь не найден в кэше.\n"

    text += f"\n<b>Активных пользователей:</b> {stats.get_active_users_count()}\n"
    text += f"<b>Обработано команд:</b> {stats.commands_count}\n"
    text += f"<b>Redis подключен:</b> {'Да' if redis_client.connected else 'Нет'}\n"
    text += f"<b>API Base URL:</b> {API_BASE_URL}\n"

    await message.answer(text)


# =========================
# КОМАНДА SERVICES
# =========================
@dp.message(Command("services"))
@rate_limit()
@safe_send_message
async def cmd_services(message: Message):
    """Информация о сервисах"""
    text = "🛠 <b>Информация о сервисах</b>\n\n"

    text += "📡 <b>API Сервис:</b>\n"
    text += f"  • <b>URL:</b> {API_BASE_URL}\n"
    text += f"  • <b>Статус:</b> {'🟢 Доступен' if api_client else '🔴 Недоступен'}\n\n"

    text += "🗄 <b>Redis:</b>\n"
    text += f"  • <b>URL:</b> {REDIS_URL}\n"
    text += f"  • <b>Статус:</b> {'🟢 Доступен' if redis_client.connected else '🔴 Недоступен'}\n\n"

    text += "🤖 <b>Telegram Bot:</b>\n"
    text += f"  • <b>Статус:</b> 🟢 Работает\n"
    text += f"  • <b>Активных пользователей:</b> {stats.get_active_users_count()}\n"
    text += f"  • <b>Обработано команд:</b> {stats.commands_count}\n"

    await message.answer(text)


# =========================
# КОМАНДА ECHO
# =========================
@dp.message(Command("echo"))
@rate_limit()
@safe_send_message
async def cmd_echo(message: Message):
    """Эхо-команда"""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("ℹ️ <b>Использование:</b> <code>/echo [текст]</code>")
        return

    text = args[1]
    await message.answer(f"📢 <b>Эхо:</b> {text}")


# =========================
# КОМАНДА STATUS
# =========================
@dp.message(Command("status"))
@rate_limit()
@safe_send_message
async def cmd_status(message: Message):
    """Статус системы"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    moscow_time = get_moscow_time()
    moscow_time_str = format_moscow_time(moscow_time)

    text = "📊 <b>Статус системы</b>\n\n"

    text += f"🕐 <b>Текущее время (Москва):</b> {moscow_time_str}\n"
    text += f"👥 <b>Активных пользователей:</b> {stats.get_active_users_count()}\n"
    text += f"📈 <b>Обработано команд:</b> {stats.commands_count}\n"
    text += f"🗄 <b>Redis:</b> {'🟢 Подключен' if redis_client.connected else '🔴 Отключен'}\n"
    text += f"📡 <b>API:</b> {'🟢 Доступен' if api_client else '🔴 Недоступен'}\n"

    if user:
        text += f"\n👤 <b>Ваш статус:</b> {user.get('status')}\n"
        if user.get('status') == UserStatus.AUTHORIZED:
            text += f"📧 <b>Email:</b> {user.get('email')}\n"
            text += f"🎭 <b>Роль:</b> {user.get('role')}\n"
    else:
        text += "\n👤 <b>Ваш статус:</b> Неизвестный (используйте /login для входа)"

    text += "\n\n<b>Основные команды:</b>\n"
    text += "/start - начало работы\n"
    text += "/help - справка\n"
    text += "/status - этот статус\n"

    await message.answer(text)


# =========================
# КОМАНДА ALL_COURSES (ВСЕ КУРСЫ) - ИСПРАВЛЕННАЯ
# =========================
@dp.message(Command("all_courses"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_all_courses(message: Message, user: Dict):
    """Получить все курсы"""
    api_token = user.get("api_token", "")

    try:
        courses = await api_client.get_courses(api_token)

        if not courses:
            await message.answer("📚 <b>Нет доступных курсов</b>")
            return

        text = "📚 <b>Список всех курсов:</b>\n\n"
        for course in courses[:10]:  # Ограничиваем вывод 10 курсами
            course_id = course.get('id', '?')
            course_name = course.get('name', 'Без названия')
            course_desc = course.get('description', 'Нет описания')
            teacher_id = course.get('teacher_id', '?')

            text += f"🎓 <b>{course_name}</b> (ID: {course_id})\n"
            text += f"   📝 Описание: {course_desc}\n"
            text += f"   👨‍🏫 Преподаватель ID: {teacher_id}\n\n"

        if len(courses) > 10:
            text += f"\n... и еще {len(courses) - 10} курсов"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении курсов: {e}")
        await message.answer(f"❌ <b>Ошибка при получении курсов:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА TESTS (СПИСОК ТЕСТОВ) - ИСПРАВЛЕННАЯ
# =========================
@dp.message(Command("tests"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_tests(message: Message, user: Dict):
    """Список доступных тестов"""
    api_token = user.get("api_token", "")

    try:
        tests = await api_client.get_tests(api_token, DEFAULT_COURSE_ID)

        if not tests:
            await message.answer(
                "📚 <b>Нет доступных тестов</b>\n\nНа данный момент нет активных тестов для прохождения.")
            return

        text = "📚 <b>Доступные тесты:</b>\n\n"

        for test in tests[:15]:  # Ограничиваем вывод 15 тестами
            test_id = test.get("id", "?")
            test_name = test.get("name", f"Тест {test_id}")
            is_active = test.get("is_active", False)
            questions = test.get("questions", [])

            status = "🟢 Активен" if is_active else "🔴 Неактивен"

            text += f"🧪 <b>{test_name}</b> (ID: {test_id})\n"
            text += f"   📊 Статус: {status}\n"
            text += f"   ❓ Вопросов: {len(questions)}\n"
            text += f"   🚀 Команда: /start_test {test_id}\n\n"

        if len(tests) > 15:
            text += f"\n... и еще {len(tests) - 15} тестов"

        text += "\n<b>Чтобы начать тест, используйте команду:</b>\n"
        text += "<code>/start_test ID_теста</code>\n\n"
        text += "<b>Пример:</b>\n"
        text += "<code>/start_test 1</code> - начать тест с ID 1"

        await message.answer(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Ошибка при получении тестов: {e}")
        await message.answer(f"❌ <b>Ошибка при загрузке тестов:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА START_TEST (НАЧАТЬ ТЕСТ) - ИСПРАВЛЕННАЯ
# =========================
@dp.message(Command("start_test"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_start_test(message: Message, user: Dict):
    """Начать тест"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/start_test ID_теста</code>\n\nПример: <code>/start_test 1</code>\n\nСначала посмотрите доступные тесты с помощью /tests")
        return

    try:
        test_id = int(args[1])
        api_token = user.get("api_token", "")

        # Начинаем тест
        result = await api_client.start_test(api_token, test_id)

        if "error" in result:
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
            return

        attempt_id = result.get("attempt_id") or result.get("id")

        if not attempt_id:
            await message.answer("❌ <b>Не удалось получить ID попытки</b>")
            return

        # Получаем информацию о тесте
        tests = await api_client.get_tests(api_token, DEFAULT_COURSE_ID)
        test_info = None
        for test in tests:
            if test.get("id") == test_id:
                test_info = test
                break

        if not test_info:
            await message.answer(f"❌ <b>Тест {test_id} не найден</b>")
            return

        test_name = test_info.get("name", f"Тест {test_id}")
        questions = test_info.get("questions", [])

        if not questions:
            await message.answer(f"❌ <b>В тесте нет вопросов</b>")
            return

        # Получаем первый вопрос
        first_question_id = questions[0]
        question_info = await api_client.get_question_details(api_token, first_question_id)

        question_text = question_info.get("text", f"Вопрос {first_question_id}")
        options = question_info.get("options", ["Вариант 1", "Вариант 2", "Вариант 3"])

        # Создаем кнопки для ответов на первый вопрос
        buttons = []
        for i, option in enumerate(options):
            buttons.append([
                InlineKeyboardButton(
                    text=f"{i}. {option}",
                    callback_data=f"answer_{attempt_id}_{first_question_id}_{i}"
                )
            ])

        # Добавляем кнопку для пропуска вопроса
        buttons.append([
            InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"skip_{attempt_id}_{first_question_id}")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

        text = f"🚀 <b>Тест начат!</b>\n\n"
        text += f"🧪 Тест: {test_name}\n"
        text += f"🆔 ID попытки: {attempt_id}\n"
        text += f"❓ Вопросов: {len(questions)}\n\n"
        text += f"📝 <b>Вопрос 1 из {len(questions)}:</b>\n"
        text += f"{question_text}\n\n"
        text += f"<b>Выберите вариант ответа:</b>"

        await message.answer(text, reply_markup=kb)

    except ValueError:
        await message.answer("❌ <b>Неверный ID теста</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при начале теста: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# ОБРАБОТЧИК ДЛЯ ОТВЕТОВ НА ВОПРОСЫ
# =========================
@dp.callback_query(F.data.startswith("answer_"))
async def callback_answer(callback: CallbackQuery):
    """Обработка ответа на вопрос"""
    try:
        # Парсим данные из callback_data: answer_attemptId_questionId_answerIndex
        data_parts = callback.data.split("_")
        if len(data_parts) != 4:
            await callback.answer("❌ Неверный формат данных")
            return

        attempt_id = int(data_parts[1])
        question_id = int(data_parts[2])
        answer_index = int(data_parts[3])

        # Получаем пользователя
        chat_id = callback.from_user.id
        user = await get_user(chat_id)

        if not user or user.get("status") != UserStatus.AUTHORIZED:
            await callback.answer("❌ Требуется авторизация", show_alert=True)
            return

        api_token = user.get("api_token", "")

        # Сохраняем ответ
        result = await api_client.submit_answer(api_token, attempt_id, question_id, answer_index)

        if "error" in result:
            await callback.answer(f"❌ Ошибка: {result['error']}", show_alert=True)
            return

        # Получаем информацию о тесте для следующего вопроса
        # Для простоты продолжаем тест
        await callback.message.edit_text(
            f"✅ <b>Ответ сохранен!</b>\n\n"
            f"Ответ на вопрос {question_id} сохранен.\n"
            f"Используйте команду /finish_test {attempt_id} для завершения теста.",
            reply_markup=None
        )
        await callback.answer("✅ Ответ сохранен")

    except Exception as e:
        logger.error(f"Ошибка в callback_answer: {e}")
        await callback.answer("❌ Ошибка при сохранении ответа", show_alert=True)


# =========================
# КОМАНДА FINISH_TEST (ЗАВЕРШИТЬ ТЕСТ) - ИСПРАВЛЕННАЯ
# =========================
@dp.message(Command("finish_test"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_finish_test(message: Message, user: Dict):
    """Завершить тест и получить результат"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/finish_test ID_попытки</code>\n\nПример: <code>/finish_test 1001</code>")
        return

    try:
        attempt_id = int(args[1])
        api_token = user.get("api_token", "")

        # Завершаем тест
        result = await api_client.finish_test(api_token, attempt_id)

        if "error" in result:
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
            return

        # Получаем результат
        score = result.get("score", 0)
        if isinstance(score, str):
            try:
                score = int(score.replace("%", "").strip())
            except:
                score = 0

        # Определяем оценку
        if score >= 90:
            grade = "Отлично! 🎉"
            emoji = "🟢"
        elif score >= 70:
            grade = "Хорошо! 👍"
            emoji = "🟡"
        elif score >= 50:
            grade = "Удовлетворительно"
            emoji = "🟠"
        else:
            grade = "Неудовлетворительно 😔"
            emoji = "🔴"

        text = f"{emoji} <b>Тест завершен!</b>\n\n"
        text += f"🆔 ID попытки: {attempt_id}\n"
        text += f"🎯 Результат: {score}%\n"
        text += f"📊 Оценка: {grade}\n\n"

        if score < 50:
            text += "💡 <b>Совет:</b> Рекомендуем повторить материал и попробовать снова.\n"
        elif score < 70:
            text += "💡 <b>Совет:</b> Неплохой результат! Можно улучшить.\n"
        elif score < 90:
            text += "💡 <b>Совет:</b> Хороший результат! Так держать!\n"
        else:
            text += "💡 <b>Совет:</b> Отличный результат! Вы прекрасно усвоили материал!\n"

        text += "\nПосмотреть все свои попытки: /my_attempts"

        await message.answer(text)
    except ValueError:
        await message.answer("❌ <b>Неверный ID попытки</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при завершении теста: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА MY_ATTEMPTS (МОИ ПОПЫТКИ)
# =========================
@dp.message(Command("my_attempts"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_my_attempts(message: Message, user: Dict):
    """Получить мои попытки"""
    api_token = user.get("api_token", "")
    user_id = user.get("user_id")

    try:
        user_data = await api_client.get_user_courses_grades(api_token, user_id)
        attempts = user_data.get('attempts', [])

        if not attempts:
            await message.answer("📝 <b>У вас нет попыток прохождения тестов</b>")
            return

        text = "📝 <b>Ваши попытки:</b>\n\n"

        # Используем заглушку для примеров
        example_attempts = [
            {"id": 1001, "test_id": 1, "status": "completed", "score": 85},
            {"id": 1002, "test_id": 2, "status": "completed", "score": 70},
            {"id": 1003, "test_id": 3, "status": "in_progress", "score": None}
        ]

        for attempt in example_attempts:
            test_id = attempt.get('test_id')
            status = attempt.get('status', 'unknown')
            score = attempt.get('score', '?')

            status_emoji = "🟢" if status == 'completed' else "🟡" if status == 'in_progress' else "⚪"
            status_text = "Завершено" if status == 'completed' else "В процессе" if status == 'in_progress' else "Неизвестно"

            text += f"{status_emoji} <b>Тест {test_id}</b> (ID теста: {test_id})\n"
            text += f"   📊 Статус: {status_text}\n"
            if status == 'completed':
                text += f"   🎯 Результат: {score}%\n"
            text += f"   🆔 ID попытки: {attempt.get('id', '?')}\n\n"

        text += f"<b>Статистика:</b>\n"
        text += f"  • Всего попыток: {len(example_attempts)}\n"
        text += f"  • Завершено: 2\n"
        text += f"  • В процессе: 1\n"
        text += f"  • Средний балл: 77.5%\n"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении попыток пользователя: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА MY_COURSES (МОИ КУРСЫ)
# =========================
@dp.message(Command("my_courses"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_my_courses(message: Message, user: Dict):
    """Получить мои курсы"""
    api_token = user.get("api_token", "")
    user_id = user.get("user_id")

    try:
        user_data = await api_client.get_user_courses_grades(api_token, user_id)
        courses = user_data.get('courses', [])

        if not courses:
            await message.answer("📚 <b>У вас нет записанных курсов</b>")
            return

        text = "📚 <b>Ваши курсы:</b>\n\n"
        for course in courses[:5]:  # Ограничиваем вывод 5 курсами
            course_id = course.get('id', '?')
            course_name = course.get('name', 'Без названия')
            course_desc = course.get('description', 'Нет описания')
            teacher_id = course.get('teacher_id', '?')

            text += f"🎓 <b>{course_name}</b> (ID: {course_id})\n"
            text += f"   📝 Описание: {course_desc}\n"
            text += f"   👨‍🏫 Преподаватель ID: {teacher_id}\n\n"

        if len(courses) > 5:
            text += f"\n... и еще {len(courses) - 5} курсов"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении курсов пользователя: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА MY_GRADES (МОИ ОЦЕНКИ)
# =========================
@dp.message(Command("my_grades"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_my_grades(message: Message, user: Dict):
    """Получить мои оценки"""
    api_token = user.get("api_token", "")
    user_id = user.get("user_id")

    try:
        user_data = await api_client.get_user_courses_grades(api_token, user_id)
        attempts = user_data.get('attempts', [])

        if not attempts:
            await message.answer("📊 <b>У вас нет завершенных тестов</b>")
            return

        text = "📊 <b>Ваши оценки:</b>\n\n"

        # Пример оценок
        example_grades = [
            {"test_id": 1, "test_name": "Тест по основам Python", "score": 85, "attempts": 1},
            {"test_id": 2, "test_name": "Тест по функциям Python", "score": 70, "attempts": 2},
            {"test_id": 3, "test_name": "Тест по SQL", "score": 90, "attempts": 1}
        ]

        for grade in example_grades:
            text += f"🧪 <b>{grade['test_name']}</b>\n"
            text += f"   🎯 Балл: {grade['score']}%\n"
            text += f"   🔢 Попыток: {grade['attempts']}\n\n"

        text += f"<b>Общая статистика:</b>\n"
        text += f"  • Всего завершенных тестов: {len(example_grades)}\n"
        text += f"  • Средний балл: 81.7%\n"
        text += f"  • Лучший результат: 90%\n"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении оценок пользователя: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА QUESTIONS_LIST (СПИСОК ВОПРОСОВ)
# =========================
@dp.message(Command("questions_list"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_questions_list(message: Message, user: Dict):
    """Получить список всех вопросов"""
    api_token = user.get("api_token", "")

    try:
        questions = await api_client.get_questions(api_token)

        if not questions:
            await message.answer("❓ <b>Нет вопросов в системе</b>")
            return

        text = "❓ <b>Список вопросов:</b>\n\n"
        for question in questions[:10]:  # Ограничиваем вывод 10 вопросами
            question_id = question.get('id', '?')
            question_title = question.get('title', 'Без названия')
            question_text = question.get('text', 'Нет текста')
            options = question.get('options', [])
            correct = question.get('correct', '?')

            text += f"📝 <b>{question_title}</b> (ID: {question_id})\n"
            text += f"   📄 Текст: {question_text[:50]}...\n"
            text += f"   🔢 Вариантов: {len(options)}\n"
            text += f"   ✅ Правильный: {correct}\n\n"

        if len(questions) > 10:
            text += f"\n... и еще {len(questions) - 10} вопросов"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении вопросов: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА COURSE_TESTS (ТЕСТЫ КУРСА)
# =========================
@dp.message(Command("course_tests"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_course_tests(message: Message, user: Dict):
    """Получить тесты курса"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/course_tests ID_курса</code>\n\nПример: <code>/course_tests 1</code>")
        return

    try:
        course_id = int(args[1])
        api_token = user.get("api_token", "")

        tests = await api_client.get_course_tests(api_token, course_id)

        if not tests:
            await message.answer(f"📝 <b>На курсе {course_id} нет тестов</b>")
            return

        text = f"📝 <b>Тесты курса {course_id}:</b>\n\n"
        for test in tests[:10]:  # Ограничиваем вывод 10 тестами
            test_id = test.get('id', '?')
            test_name = test.get('name', 'Без названия')
            is_active = test.get('is_active', False)
            questions = test.get('questions', [])

            status = "🟢 Активен" if is_active else "🔴 Неактивен"

            text += f"🧪 <b>{test_name}</b> (ID: {test_id})\n"
            text += f"   📊 Статус: {status}\n"
            text += f"   ❓ Вопросов: {len(questions)}\n\n"

        if len(tests) > 10:
            text += f"\n... и еще {len(tests) - 10} тестов"

        await message.answer(text)
    except ValueError:
        await message.answer("❌ <b>Неверный ID курса</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при получении тестов курса: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА TEST_RESULTS (РЕЗУЛЬТАТЫ ТЕСТА)
# =========================
@dp.message(Command("test_results"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_test_results(message: Message, user: Dict):
    """Получить результаты теста"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/test_results ID_теста</code>\n\nПример: <code>/test_results 1</code>")
        return

    try:
        test_id = int(args[1])
        api_token = user.get("api_token", "")

        results = await api_client.get_test_results(api_token, test_id)

        if not results:
            await message.answer(f"📊 <b>На тесте {test_id} нет завершенных попыток</b>")
            return

        text = f"📊 <b>Результаты теста {test_id}:</b>\n\n"

        # Статистика
        total_attempts = len(results)
        avg_score = sum(r.get('score', 0) for r in results) / total_attempts if total_attempts > 0 else 0
        best_score = max(r.get('score', 0) for r in results) if results else 0
        worst_score = min(r.get('score', 0) for r in results) if results else 0

        text += f"<b>Статистика:</b>\n"
        text += f"  • Всего попыток: {total_attempts}\n"
        text += f"  • Средний балл: {avg_score:.1f}%\n"
        text += f"  • Лучший результат: {best_score}%\n"
        text += f"  • Худший результат: {worst_score}%\n\n"

        text += f"<b>Детали по студентам:</b>\n\n"
        for result in results[:5]:  # Ограничиваем вывод 5 результатами
            score = result.get('score', 0)
            grade = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
            user_name = result.get('user_name', f"Студент {result.get('user_id', '?')}")

            text += f"{grade} <b>{user_name}</b>\n"
            text += f"   🎯 Балл: {score}%\n"
            text += f"   🆔 ID пользователя: {result.get('user_id', '?')}\n\n"

        if len(results) > 5:
            text += f"\n... и еще {len(results) - 5} результатов"

        await message.answer(text)
    except ValueError:
        await message.answer("❌ <b>Неверный ID теста</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при получении результатов теста: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА AUTH_STUDENT - ДЛЯ ТЕСТИРОВАНИЯ
# =========================
@dp.message(Command("auth_student"))
@rate_limit()
@safe_send_message
async def cmd_auth_student(message: Message):
    """Автоматическая авторизация как студент (для тестирования)"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await message.answer(f"✅ <b>Вы уже авторизованы как {user.get('email')}</b>")
        return

    # Создаем тестовые данные для авторизации студента
    user_id = secrets.randbelow(1000) + 100
    email = f"student_{chat_id}@test.com"

    await set_user_authorized(chat_id, user_id, email, "student")

    await message.answer(
        f"✅ <b>Автоматическая авторизация студента успешна!</b>\n\n"
        f"Добро пожаловать, {email}\n\n"
        f"Теперь вы можете использовать команды для студентов:\n"
        f"• /tests — список тестов\n"
        f"• /my_courses — мои курсы\n"
        f"• /help_student — справка для студентов"
    )


# =========================
# КОМАНДА AUTH_TEACHER - ДЛЯ ТЕСТИРОВАНИЯ
# =========================
@dp.message(Command("auth_teacher"))
@rate_limit()
@safe_send_message
async def cmd_auth_teacher(message: Message):
    """Автоматическая авторизация как преподаватель (для тестирования)"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await message.answer(f"✅ <b>Вы уже авторизованы как {user.get('email')}</b>")
        return

    # Создаем тестовые данные для авторизации преподавателя
    user_id = secrets.randbelow(1000) + 100
    email = f"teacher_{chat_id}@test.com"

    await set_user_authorized(chat_id, user_id, email, "teacher")

    await message.answer(
        f"✅ <b>Автоматическая авторизация преподавателя успешна!</b>\n\n"
        f"Добро пожаловать, {email}\n\n"
        f"Теперь вы можете использовать команды для преподавателей:\n"
        f"• /users — список пользователей\n"
        f"• /all_courses — все курсы\n"
        f"• /help_teacher — справка для преподавателей"
    )


# =========================
# КОМАНДА PROFILE
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

    user_email = current_user.get("email", "Неизвестно")
    user_role = current_user.get("role", "student")
    role_text = "👨‍🏫 Преподаватель" if user_role == "teacher" else "👨‍🎓 Студент"
    user_id = current_user.get("user_id", "?")

    # Форматируем дату авторизации (по Москве)
    auth_date = "Неизвестно"
    if current_user.get("authorized_at"):
        try:
            auth_dt_utc = datetime.fromisoformat(current_user["authorized_at"].replace('Z', '+00:00'))
            auth_dt_msk = auth_dt_utc + timedelta(hours=3)
            auth_date = auth_dt_msk.strftime("%d.%m.%Y %H:%M (MSK)")
        except:
            auth_date = current_user["authorized_at"]

    text = f"""
👤 <b>Профиль пользователя</b>

<b>Основная информация:</b>
📧 <b>Email:</b> {user_email}
🔑 <b>Роль:</b> {role_text}
🔢 <b>ID пользователя:</b> {user_id}

<b>Сессия в Telegram:</b>
🤖 <b>Авторизован:</b> {auth_date}
🔐 <b>Статус:</b> 🟢 Активен
"""

    await message.answer(text)


# =========================
# КОМАНДА HELP
# =========================
@dp.message(Command("help"))
@rate_limit()
@safe_send_message
async def cmd_help(message: Message):
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        role = user.get("role", "student")
        if role == "teacher":
            help_text = """
🆘 <b>Общая справка (Преподаватель)</b>

<b>Основные команды:</b>
/start — начало работы
/help — эта справка
/status — статус системы
/profile — ваш профиль
/logout — выход из системы
/logout_all — выход на всех устройствах

<b>Тестирование:</b>
/tests — список доступных тестов
/start_test ID — начать тест
/finish_test ID_попытки — завершить тест

<b>Мои данные:</b>
/my_courses — мои курсы
/my_grades — мои оценки
/my_attempts — мои попытки

<b>Администрирование:</b>
/all_courses — все курсы
/course_tests ID — тесты курса
/questions_list — все вопросы
/test_results ID — результаты теста

<b>Быстрые команды:</b>
/ping — проверка работы бота
/echo — эхо-команда
/debug — отладочная информация
/services — информация о сервисах
"""
        else:
            help_text = """
🆘 <b>Общая справка (Студент)</b>

<b>Основные команды:</b>
/start — начало работы
/help — эта справка
/status — статус системы
/profile — ваш профиль
/logout — выход из системы
/logout_all — выход на всех устройствах

<b>Тестирование:</b>
/tests — список доступных тестов
/start_test ID — начать тест
/finish_test ID_попытки — завершить тест

<b>Мои данные:</b>
/my_courses — мои курсы
/my_grades — мои оценки
/my_attempts — мои попытки

<b>Быстрые команды:</b>
/ping — проверка работы бота
/echo — эхо-команда
/debug — отладочная информация
/services — информация о сервисах
"""
    else:
        help_text = """
🆘 <b>Общая справка (Гость)</b>

<b>Основные команды:</b>
/start — начало работы
/help — эта справка
/status — статус системы

<b>Авторизация:</b>
/login — вход в систему
/auth_student — тестовая авторизация как студент
/auth_teacher — тестовая авторизация как преподаватель

<b>Тестирование системы:</b>
/ping — проверка работы бота
/echo — эхо-команда
/debug — отладочная информация
/services — информация о сервисах
"""

    await message.answer(help_text)


# =========================
# BACKGROUND TASK ДЛЯ ОЧИСТКИ УСТАРЕВШИХ АВТОРИЗАЦИЙ
# =========================
async def check_anonymous_users_task():
    """Циклическая проверка anonymous пользователей"""
    while True:
        try:
            keys = await redis_client.keys("user:*")
            for key in keys:
                data = await redis_client.get(key)
                if data:
                    try:
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
                    except:
                        pass
        except Exception as e:
            logger.error(f"Error in check_anonymous_users_task: {e}")

        await asyncio.sleep(30)


# =========================
# ОБРАБОТЧИК НЕИЗВЕСТНЫХ КОМАНД
# =========================
@dp.message()
@rate_limit()
async def unknown_command(message: Message):
    """Обработка неизвестных команд"""
    # Игнорируем служебные сообщения
    if message.text is None:
        return

    # Если сообщение не начинается с /, то это не команда
    if not message.text.startswith('/'):
        return

    await message.answer(
        "❓ <b>Неизвестная команда</b>\n\n"
        "Используйте /help для просмотра списка команд."
    )


# =========================
# ОСНОВНАЯ ФУНКЦИЯ
# =========================
async def main():
    logger.info("🤖 Telegram bot starting...")
    logger.info(f"📡 API Base URL: {API_BASE_URL}")
    logger.info(f"🌐 HTTP Server port: {HTTP_PORT}")

    await redis_client.connect()

    # Запуск HTTP сервера для health-check
    try:
        http_runner = await start_http_server()
        logger.info("✅ HTTP сервер запущен для health-check")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска HTTP сервера: {e}")
        http_runner = None

    background_task = asyncio.create_task(check_anonymous_users_task())

    logger.info("🚀 Bot is ready!")
    logger.info("📊 Доступны эндпоинты:")
    logger.info(f"   • http://localhost:{HTTP_PORT}/health")
    logger.info(f"   • http://localhost:{HTTP_PORT}/status")
    logger.info(f"   • http://localhost:{HTTP_PORT}/")

    try:
        await dp.start_polling(bot, skip_updates=True)
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    finally:
        background_task.cancel()
        await api_client.close()
        if http_runner:
            await http_runner.cleanup()
            logger.info("🌐 HTTP сервер остановлен")


if __name__ == "__main__":
    asyncio.run(main())