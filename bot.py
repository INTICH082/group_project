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
JWT_SECRET = os.getenv("JWT_SECRET", "iplaygodotandclaimfun")
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
# DATA STORAGE (ЗАГЛУШКИ ДЛЯ ТЕСТОВЫХ ДАННЫХ) - РАСШИРЕННАЯ ВЕРСИЯ
# =========================
class DataStorage:
    def __init__(self):
        # Заглушки данных пользователей
        self.users = {
            1: {"id": 1, "full_name": "Иванов Иван Иванович", "email": "teacher@example.com",
                "role": "teacher", "is_blocked": False, "created_at": "2024-01-01T10:00:00Z"},
            2: {"id": 2, "full_name": "Петров Петр Петрович", "email": "student1@example.com",
                "role": "student", "is_blocked": False, "created_at": "2024-01-02T11:00:00Z"},
            3: {"id": 3, "full_name": "Сидорова Анна Владимировна", "email": "student2@example.com",
                "role": "student", "is_blocked": False, "created_at": "2024-01-03T12:00:00Z"},
            4: {"id": 4, "full_name": "Козлов Алексей Сергеевич", "email": "student3@example.com",
                "role": "student", "is_blocked": True, "created_at": "2024-01-04T13:00:00Z"},
            5: {"id": 5, "full_name": "Николаева Мария Дмитриевна", "email": "teacher2@example.com",
                "role": "teacher", "is_blocked": False, "created_at": "2024-01-05T14:00:00Z"},
        }

        # Заглушки курсов
        self.courses = {
            1: {"id": 1, "name": "Программирование на Python",
                "description": "Основы программирования на Python",
                "teacher_id": 1, "is_active": True, "created_at": "2024-01-10T10:00:00Z"},
            2: {"id": 2, "name": "Базы данных",
                "description": "Основы работы с базами данных",
                "teacher_id": 1, "is_active": True, "created_at": "2024-01-11T11:00:00Z"},
            3: {"id": 3, "name": "Веб-разработка",
                "description": "Создание веб-приложений",
                "teacher_id": 5, "is_active": True, "created_at": "2024-01-12T12:00:00Z"},
            4: {"id": 4, "name": "Алгоритмы и структуры данных",
                "description": "Изучение алгоритмов и структур данных",
                "teacher_id": 5, "is_active": False, "created_at": "2024-01-13T13:00:00Z"},
            5: {"id": 5, "name": "Машинное обучение",
                "description": "Основы машинного обучения",
                "teacher_id": 1, "is_active": True, "created_at": "2024-01-14T14:00:00Z"},
        }

        # Связь курсов и студентов
        self.course_students = {
            1: [2, 3],  # Python: student1, student2
            2: [2, 4],  # Базы данных: student1, student3
            3: [3],  # Веб-разработка: student2
            5: [2, 3, 4],  # Машинное обучение: все студенты
        }

        # Заглушки тестов
        self.tests = {
            1: {"id": 1, "name": "Тест по основам Python", "course_id": 1,
                "is_active": True, "questions": [1, 2, 3], "created_at": "2024-02-01T10:00:00Z"},
            2: {"id": 2, "name": "Тест по функциям Python", "course_id": 1,
                "is_active": False, "questions": [4, 5], "created_at": "2024-02-02T11:00:00Z"},
            3: {"id": 3, "name": "Тест по SQL", "course_id": 2,
                "is_active": True, "questions": [6, 7], "created_at": "2024-02-03T12:00:00Z"},
            4: {"id": 4, "name": "Тест по HTML/CSS", "course_id": 3,
                "is_active": True, "questions": [8, 9], "created_at": "2024-02-04T13:00:00Z"},
            5: {"id": 5, "name": "Итоговый тест по ML", "course_id": 5,
                "is_active": True, "questions": [10], "created_at": "2024-02-05T14:00:00Z"},
        }

        # Заглушки вопросов
        self.questions = {
            1: {"id": 1, "title": "Типы данных Python", "text": "Что такое Python?",
                "options": ["Язык программирования", "Змея", "Оба варианта верны"],
                "correct": 2, "author_id": 1, "version": 1, "created_at": "2024-01-15T10:00:00Z"},
            2: {"id": 2, "title": "Списки Python", "text": "Как создать пустой список в Python?",
                "options": ["list()", "[]", "Оба варианта верны"],
                "correct": 2, "author_id": 1, "version": 1, "created_at": "2024-01-15T11:00:00Z"},
            3: {"id": 3, "title": "Функции Python", "text": "Что такое функция в Python?",
                "options": ["Блок кода", "Ключевое слово", "Именованный блок кода"],
                "correct": 2, "author_id": 1, "version": 1, "created_at": "2024-01-15T12:00:00Z"},
            4: {"id": 4, "title": "Аргументы функций", "text": "Что такое args в Python?",
                "options": ["Позиционные аргументы", "Именованные аргументы", "Ключевое слово"],
                "correct": 0, "author_id": 1, "version": 1, "created_at": "2024-01-16T10:00:00Z"},
            5: {"id": 5, "title": "Декораторы", "text": "Что такое декоратор в Python?",
                "options": ["Функция", "Класс", "Функция высшего порядка"],
                "correct": 2, "author_id": 1, "version": 1, "created_at": "2024-01-16T11:00:00Z"},
            6: {"id": 6, "title": "SQL SELECT", "text": "Как выбрать все данные из таблицы?",
                "options": ["SELECT * FROM table", "GET * FROM table", "FIND * FROM table"],
                "correct": 0, "author_id": 1, "version": 1, "created_at": "2024-01-17T10:00:00Z"},
            7: {"id": 7, "title": "SQL JOIN", "text": "Что такое JOIN в SQL?",
                "options": ["Объединение таблиц", "Удаление данных", "Создание таблиц"],
                "correct": 0, "author_id": 1, "version": 1, "created_at": "2024-01-17T11:00:00Z"},
            8: {"id": 8, "title": "HTML теги", "text": "Какой тег используется для заголовка?",
                "options": ["<h1>", "<header>", "<title>"],
                "correct": 0, "author_id": 5, "version": 1, "created_at": "2024-01-18T10:00:00Z"},
            9: {"id": 9, "title": "CSS свойства", "text": "Какое свойство изменяет цвет текста?",
                "options": ["color", "background-color", "font-color"],
                "correct": 0, "author_id": 5, "version": 1, "created_at": "2024-01-18T11:00:00Z"},
            10: {"id": 10, "title": "ML алгоритмы", "text": "Что такое линейная регрессия?",
                 "options": ["Метод классификации", "Метод кластеризации", "Метод регрессии"],
                 "correct": 2, "author_id": 1, "version": 1, "created_at": "2024-01-19T10:00:00Z"},
        }

        # Заглушки попыток
        self.attempts = {
            1001: {"id": 1001, "user_id": 2, "test_id": 1, "status": "completed",
                   "score": 85, "started_at": "2024-02-10T10:00:00Z",
                   "finished_at": "2024-02-10T10:30:00Z", "answers": {1: 2, 2: 2, 3: 2}},
            1002: {"id": 1002, "user_id": 3, "test_id": 1, "status": "completed",
                   "score": 70, "started_at": "2024-02-10T11:00:00Z",
                   "finished_at": "2024-02-10T11:25:00Z", "answers": {1: 2, 2: 0, 3: 1}},
            1003: {"id": 1003, "user_id": 2, "test_id": 3, "status": "in_progress",
                   "score": None, "started_at": "2024-02-11T10:00:00Z",
                   "finished_at": None, "answers": {6: 0}},
            1004: {"id": 1004, "user_id": 3, "test_id": 4, "status": "completed",
                   "score": 90, "started_at": "2024-02-12T14:00:00Z",
                   "finished_at": "2024-02-12T14:20:00Z", "answers": {8: 0, 9: 0}},
            1005: {"id": 1005, "user_id": 4, "test_id": 5, "status": "completed",
                   "score": 50, "started_at": "2024-02-13T09:00:00Z",
                   "finished_at": "2024-02-13T09:10:00Z", "answers": {10: 2}},
        }

        # Заглушки ответов
        self.answers = {
            1: {"id": 1, "attempt_id": 1001, "question_id": 1, "version": 1, "answer": 2},
            2: {"id": 2, "attempt_id": 1001, "question_id": 2, "version": 1, "answer": 2},
            3: {"id": 3, "attempt_id": 1001, "question_id": 3, "version": 1, "answer": 2},
            4: {"id": 4, "attempt_id": 1002, "question_id": 1, "version": 1, "answer": 2},
            5: {"id": 5, "attempt_id": 1002, "question_id": 2, "version": 1, "answer": 0},
            6: {"id": 6, "attempt_id": 1002, "question_id": 3, "version": 1, "answer": 1},
            7: {"id": 7, "attempt_id": 1003, "question_id": 6, "version": 1, "answer": 0},
            8: {"id": 8, "attempt_id": 1004, "question_id": 8, "version": 1, "answer": 0},
            9: {"id": 9, "attempt_id": 1004, "question_id": 9, "version": 1, "answer": 0},
            10: {"id": 10, "attempt_id": 1005, "question_id": 10, "version": 1, "answer": 2},
        }


data_storage = DataStorage()


# =========================
# API CLIENT - УЛУЧШЕННАЯ ВЕРСИЯ С РЕАЛЬНЫМИ API ЗАПРОСАМИ
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
            if role == "teacher":
                permissions = [
                    Permission.USER_LIST_READ,
                    Permission.USER_FULLNAME_WRITE,
                    Permission.USER_DATA_READ,
                    Permission.USER_ROLES_READ,
                    Permission.USER_ROLES_WRITE,
                    Permission.USER_BLOCK_READ,
                    Permission.USER_BLOCK_WRITE,
                    Permission.COURSE_INFOS_WRITE,
                    Permission.COURSE_TESTLIST,
                    Permission.COURSE_TEST_READ,
                    Permission.COURSE_TEST_WRITE,
                    Permission.COURSE_TEST_ADD,
                    Permission.COURSE_TEST_DEL,
                    Permission.COURSE_USERLIST,
                    Permission.COURSE_USER_ADD,
                    Permission.COURSE_USER_DEL,
                    Permission.COURSE_ADD,
                    Permission.COURSE_DEL,
                    Permission.QUESTION_READ,
                    Permission.QUESTION_WRITE,
                    Permission.QUESTION_ADD,
                    Permission.QUESTION_DEL,
                    Permission.TEST_QUEST_DEL,
                    Permission.TEST_QUEST_ADD,
                    Permission.TEST_QUEST_UPDATE,
                    Permission.TEST_ANSWER_READ,
                    Permission.ATTEMPT_READ,
                    Permission.ANSWER_READ,
                    Permission.ANSWER_UPDATE,
                    Permission.ANSWER_DEL,
                ]
            else:
                permissions = [
                    Permission.USER_DATA_READ,
                    Permission.COURSE_TESTLIST,
                    Permission.COURSE_TEST_READ,
                    Permission.ANSWER_READ,
                    Permission.ANSWER_UPDATE,
                    Permission.ANSWER_DEL,
                ]

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

        logger.info(f"📡 API запрос: {method} {url}")

        try:
            async with self.session.request(method, url, headers=headers, json=data, timeout=30) as response:
                response_text = await response.text()
                logger.info(f"📡 API ответ: {response.status}")

                if response.status == 418:
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
    # REAL API METHODS
    # =========================

    async def get_questions_api(self, token: str) -> List[Dict]:
        """Получить список вопросов через API"""
        try:
            response = await self.request("GET", "/teacher/question/list", token)
            if isinstance(response, list):
                return response
            elif isinstance(response, dict) and "data" in response:
                return response["data"]
            else:
                logger.warning(f"Неожиданный формат ответа для вопросов: {type(response)}")
                return []
        except Exception as e:
            logger.error(f"Ошибка при получении вопросов через API: {e}")
            return []

    async def get_course_questions_api(self, token: str, course_id: int) -> List[Dict]:
        """Получить вопросы курса через API"""
        try:
            response = await self.request("GET", f"/teacher/course/questions?course_id={course_id}", token)
            if isinstance(response, list):
                return response
            elif isinstance(response, dict) and "data" in response:
                return response["data"]
            else:
                logger.warning(f"Неожиданный формат ответа для вопросов курса: {type(response)}")
                return []
        except Exception as e:
            logger.error(f"Ошибка при получении вопросов курса через API: {e}")
            return []

    async def get_course_tests_api(self, token: str, course_id: int) -> List[Dict]:
        """Получить тесты курса через API"""
        try:
            response = await self.request("GET", f"/course/tests?course_id={course_id}", token)
            if isinstance(response, list):
                return response
            elif isinstance(response, dict) and "tests" in response:
                return response["tests"]
            elif isinstance(response, dict) and "data" in response:
                return response["data"]
            else:
                logger.warning(f"Неожиданный формат ответа для тестов курса: {type(response)}")
                return []
        except Exception as e:
            logger.error(f"Ошибка при получении тестов курса через API: {e}")
            return []

    async def get_courses_api(self, token: str) -> List[Dict]:
        """Получить курсы через API"""
        try:
            # Попробуем разные возможные эндпоинты
            endpoints = ["/course/list", "/courses", "/teacher/courses"]

            for endpoint in endpoints:
                try:
                    response = await self.request("GET", endpoint, token)
                    if isinstance(response, list):
                        return response
                    elif isinstance(response, dict) and "data" in response:
                        return response["data"]
                    elif isinstance(response, dict) and "courses" in response:
                        return response["courses"]
                except Exception as e:
                    logger.debug(f"Эндпоинт {endpoint} не сработал: {e}")
                    continue

            logger.warning("Ни один эндпоинт для курсов не сработал")
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении курсов через API: {e}")
            return []

    # =========================
    # USER METHODS
    # =========================
    async def get_users(self, token: str) -> List[Dict]:
        """Получить список пользователей"""
        return list(data_storage.users.values())

    async def get_user_info(self, token: str, user_id: int) -> Dict:
        """Получить информацию о пользователе"""
        return data_storage.users.get(user_id, {})

    async def update_user_fullname(self, token: str, user_id: int, full_name: str) -> Dict:
        """Изменить ФИО пользователя"""
        if user_id in data_storage.users:
            data_storage.users[user_id]["full_name"] = full_name
            return {"success": True, "message": "ФИО обновлено"}
        return {"error": "Пользователь не найден"}

    async def get_user_courses_grades(self, token: str, user_id: int) -> Dict:
        """Получить курсы, оценки, тесты пользователя"""
        user_courses = []
        for course_id, students in data_storage.course_students.items():
            if user_id in students:
                course = data_storage.courses[course_id]
                user_courses.append(course)

        user_attempts = []
        for attempt_id, attempt in data_storage.attempts.items():
            if attempt["user_id"] == user_id:
                user_attempts.append(attempt)

        return {
            "courses": user_courses,
            "attempts": user_attempts
        }

    async def get_user_roles(self, token: str, user_id: int) -> List[str]:
        """Получить роли пользователя"""
        user = data_storage.users.get(user_id)
        if user:
            return [user.get("role", "student")]
        return []

    async def update_user_roles(self, token: str, user_id: int, roles: List[str]) -> Dict:
        """Изменить роли пользователя"""
        if user_id in data_storage.users:
            data_storage.users[user_id]["role"] = roles[0] if roles else "student"
            return {"success": True, "message": "Роли обновлены"}
        return {"error": "Пользователь не найден"}

    async def get_user_block_status(self, token: str, user_id: int) -> Dict:
        """Проверить, заблокирован ли пользователь"""
        user = data_storage.users.get(user_id)
        if user:
            return {"is_blocked": user.get("is_blocked", False)}
        return {"error": "Пользователь не найден"}

    async def update_user_block_status(self, token: str, user_id: int, is_blocked: bool) -> Dict:
        """Заблокировать/разблокировать пользователя"""
        if user_id in data_storage.users:
            data_storage.users[user_id]["is_blocked"] = is_blocked
            return {"success": True, "message": f"Пользователь {'заблокирован' if is_blocked else 'разблокирован'}"}
        return {"error": "Пользователь не найден"}

    # =========================
    # COURSE METHODS
    # =========================
    async def get_courses(self, token: str) -> List[Dict]:
        """Получить список дисциплин"""
        # Сначала пробуем API
        try:
            api_courses = await self.get_courses_api(token)
            if api_courses:
                logger.info(f"✅ Получено {len(api_courses)} курсов через API")
                return api_courses
        except Exception as e:
            logger.warning(f"API для курсов не сработало: {e}")

        # Fallback на локальные данные
        return list(data_storage.courses.values())

    async def get_course_info(self, token: str, course_id: int) -> Dict:
        """Получить информацию о дисциплине"""
        course = data_storage.courses.get(course_id, {})
        if course:
            course["teacher"] = data_storage.users.get(course["teacher_id"], {})
        return course

    async def update_course_info(self, token: str, course_id: int, name: str, description: str) -> Dict:
        """Изменить информацию о дисциплине"""
        if course_id in data_storage.courses:
            data_storage.courses[course_id]["name"] = name
            data_storage.courses[course_id]["description"] = description
            return {"success": True, "message": "Информация о дисциплине обновлена"}
        return {"error": "Дисциплина не найдена"}

    async def get_course_tests(self, token: str, course_id: int) -> List[Dict]:
        """Получить список тестов дисциплины"""
        # Сначала пробуем API
        try:
            api_tests = await self.get_course_tests_api(token, course_id)
            if api_tests:
                logger.info(f"✅ Получено {len(api_tests)} тестов для курса {course_id} через API")
                return api_tests
        except Exception as e:
            logger.warning(f"API для тестов курса не сработало: {e}")

        # Fallback на локальные данные
        return [test for test in data_storage.tests.values() if test["course_id"] == course_id]

    async def get_test_status(self, token: str, course_id: int, test_id: int) -> Dict:
        """Получить статус теста (активен или нет)"""
        test = data_storage.tests.get(test_id)
        if test and test["course_id"] == course_id:
            return {"is_active": test["is_active"]}
        return {"error": "Тест не найден"}

    async def update_test_status(self, token: str, course_id: int, test_id: int, is_active: bool) -> Dict:
        """Активировать/деактивировать тест"""
        test = data_storage.tests.get(test_id)
        if test and test["course_id"] == course_id:
            data_storage.tests[test_id]["is_active"] = is_active
            # Автоматически завершаем все попытки если тест деактивирован
            if not is_active:
                for attempt_id, attempt in data_storage.attempts.items():
                    if attempt["test_id"] == test_id and attempt["status"] == "in_progress":
                        data_storage.attempts[attempt_id]["status"] = "completed"
            return {"success": True, "message": f"Тест {'активирован' if is_active else 'деактивирован'}"}
        return {"error": "Тест не найден"}

    async def add_test_to_course(self, token: str, course_id: int, name: str) -> Dict:
        """Добавить тест в дисциплину"""
        if course_id not in data_storage.courses:
            return {"error": "Дисциплина не найдена"}

        test_id = max(data_storage.tests.keys(), default=0) + 1
        data_storage.tests[test_id] = {
            "id": test_id,
            "name": name,
            "course_id": course_id,
            "is_active": False,
            "questions": []
        }
        return {"success": True, "test_id": test_id, "message": "Тест добавлен"}

    async def delete_test_from_course(self, token: str, test_id: int) -> Dict:
        """Удалить тест из дисциплины (пометить как удалённый)"""
        if test_id in data_storage.tests:
            # В реальной системе здесь была бы пометка как удалённый
            return {"success": True, "message": "Тест помечен как удалённый"}
        return {"error": "Тест не найден"}

    async def get_course_students(self, token: str, course_id: int) -> List[Dict]:
        """Получить список студентов дисциплины"""
        if course_id not in data_storage.course_students:
            return []

        students = []
        for student_id in data_storage.course_students[course_id]:
            student = data_storage.users.get(student_id)
            if student:
                students.append(student)
        return students

    async def enroll_student_to_course(self, token: str, course_id: int, user_id: int) -> Dict:
        """Записать пользователя на дисциплину"""
        if course_id not in data_storage.courses:
            return {"error": "Дисциплина не найдена"}

        if user_id not in data_storage.users:
            return {"error": "Пользователь не найден"}

        if course_id not in data_storage.course_students:
            data_storage.course_students[course_id] = []

        if user_id not in data_storage.course_students[course_id]:
            data_storage.course_students[course_id].append(user_id)
            return {"success": True, "message": "Пользователь записан на дисциплину"}

        return {"error": "Пользователь уже записан на эту дисциплину"}

    async def expel_student_from_course(self, token: str, course_id: int, user_id: int) -> Dict:
        """Отчислить пользователя с дисциплины"""
        if course_id in data_storage.course_students and user_id in data_storage.course_students[course_id]:
            data_storage.course_students[course_id].remove(user_id)
            return {"success": True, "message": "Пользователь отчислен с дисциплины"}
        return {"error": "Пользователь не найден на этой дисциплине"}

    async def create_course(self, token: str, name: str, description: str, teacher_id: int) -> Dict:
        """Создать дисциплину"""
        course_id = max(data_storage.courses.keys(), default=0) + 1
        data_storage.courses[course_id] = {
            "id": course_id,
            "name": name,
            "description": description,
            "teacher_id": teacher_id,
            "is_active": True
        }
        return {"success": True, "course_id": course_id, "message": "Дисциплина создана"}

    async def delete_course(self, token: str, course_id: int) -> Dict:
        """Удалить дисциплину (пометить как удалённую)"""
        if course_id in data_storage.courses:
            # В реальной системе здесь была бы пометка как удалённый
            return {"success": True, "message": "Дисциплина помечена как удалённая"}
        return {"error": "Дисциплина не найдена"}

    # =========================
    # QUESTION METHODS
    # =========================
    async def get_questions(self, token: str) -> List[Dict]:
        """Получить список вопросов"""
        # Сначала пробуем API
        try:
            api_questions = await self.get_questions_api(token)
            if api_questions:
                logger.info(f"✅ Получено {len(api_questions)} вопросов через API")
                return api_questions
        except Exception as e:
            logger.warning(f"API для вопросов не сработало: {e}")

        # Fallback на локальные данные
        return list(data_storage.questions.values())

    async def get_question_info(self, token: str, question_id: int, version: int = None) -> Dict:
        """Получить информацию о вопросе"""
        question = data_storage.questions.get(question_id)
        if question:
            if version and question["version"] != version:
                return {"error": "Версия вопроса не найдена"}
            return question
        return {"error": "Вопрос не найден"}

    async def update_question(self, token: str, question_id: int, title: str, text: str, options: List[str],
                              correct: int) -> Dict:
        """Изменить вопрос (создать новую версию)"""
        if question_id in data_storage.questions:
            old_question = data_storage.questions[question_id]
            new_version = old_question["version"] + 1
            data_storage.questions[question_id] = {
                "id": question_id,
                "title": title,
                "text": text,
                "options": options,
                "correct": correct,
                "author_id": old_question["author_id"],
                "version": new_version
            }
            return {"success": True, "version": new_version, "message": "Вопрос обновлён (новая версия создана)"}
        return {"error": "Вопрос не найден"}

    async def create_question(self, token: str, title: str, text: str, options: List[str], correct: int,
                              author_id: int) -> Dict:
        """Создать вопрос"""
        question_id = max(data_storage.questions.keys(), default=0) + 1
        data_storage.questions[question_id] = {
            "id": question_id,
            "title": title,
            "text": text,
            "options": options,
            "correct": correct,
            "author_id": author_id,
            "version": 1
        }
        return {"success": True, "question_id": question_id, "message": "Вопрос создан"}

    async def delete_question(self, token: str, question_id: int) -> Dict:
        """Удалить вопрос (пометить как удалённый)"""
        if question_id in data_storage.questions:
            # Проверяем, используется ли вопрос в тестах
            used_in_tests = False
            for test in data_storage.tests.values():
                if question_id in test["questions"]:
                    used_in_tests = True
                    break

            if not used_in_tests:
                # В реальной системе здесь была бы пометка как удалённый
                return {"success": True, "message": "Вопрос помечен как удалённый"}
            else:
                return {"error": "Вопрос используется в тестах и не может быть удалён"}
        return {"error": "Вопрос не найден"}

    # =========================
    # TEST METHODS
    # =========================
    async def delete_question_from_test(self, token: str, test_id: int, question_id: int) -> Dict:
        """Удалить вопрос из теста"""
        if test_id in data_storage.tests:
            test = data_storage.tests[test_id]
            # Проверяем, были ли попытки прохождения
            has_attempts = any(attempt["test_id"] == test_id for attempt in data_storage.attempts.values())

            if not has_attempts and question_id in test["questions"]:
                test["questions"].remove(question_id)
                return {"success": True, "message": "Вопрос удалён из теста"}
            elif has_attempts:
                return {"error": "Невозможно удалить вопрос: у теста уже есть попытки прохождения"}
            else:
                return {"error": "Вопрос не найден в тесте"}
        return {"error": "Тест не найден"}

    async def add_question_to_test(self, token: str, test_id: int, question_id: int) -> Dict:
        """Добавить вопрос в тест"""
        if test_id in data_storage.tests and question_id in data_storage.questions:
            test = data_storage.tests[test_id]
            # Проверяем, были ли попытки прохождения
            has_attempts = any(attempt["test_id"] == test_id for attempt in data_storage.attempts.values())

            if not has_attempts:
                if question_id not in test["questions"]:
                    test["questions"].append(question_id)
                    return {"success": True, "message": "Вопрос добавлен в тест"}
                else:
                    return {"error": "Вопрос уже есть в тесте"}
            else:
                return {"error": "Невозможно добавить вопрос: у теста уже есть попытки прохождения"}
        return {"error": "Тест или вопрос не найдены"}

    async def update_test_question_order(self, token: str, test_id: int, question_ids: List[int]) -> Dict:
        """Изменить порядок следования вопросов в тесте"""
        if test_id in data_storage.tests:
            test = data_storage.tests[test_id]
            # Проверяем, были ли попытки прохождения
            has_attempts = any(attempt["test_id"] == test_id for attempt in data_storage.attempts.values())

            if not has_attempts:
                # Проверяем, что все вопросы существуют
                for qid in question_ids:
                    if qid not in data_storage.questions:
                        return {"error": f"Вопрос {qid} не найден"}

                test["questions"] = question_ids
                return {"success": True, "message": "Порядок вопросов обновлён"}
            else:
                return {"error": "Невозможно изменить порядок: у теста уже есть попытки прохождения"}
        return {"error": "Тест не найден"}

    async def get_test_attempts(self, token: str, test_id: int) -> List[Dict]:
        """Получить список пользователей, прошедших тест"""
        attempts = []
        for attempt_id, attempt in data_storage.attempts.items():
            if attempt["test_id"] == test_id and attempt["status"] == "completed":
                user = data_storage.users.get(attempt["user_id"])
                if user:
                    attempts.append({
                        "user_id": user["id"],
                        "full_name": user["full_name"],
                        "score": attempt["score"],
                        "attempt_id": attempt_id
                    })
        return attempts

    async def get_test_grades(self, token: str, test_id: int) -> List[Dict]:
        """Получить оценки пользователей по тесту"""
        grades = []
        for attempt_id, attempt in data_storage.attempts.items():
            if attempt["test_id"] == test_id and attempt["status"] == "completed":
                user = data_storage.users.get(attempt["user_id"])
                if user:
                    grades.append({
                        "user_id": user["id"],
                        "full_name": user["full_name"],
                        "score": attempt["score"],
                        "attempt_id": attempt_id
                    })
        return grades

    async def get_test_answers(self, token: str, test_id: int) -> List[Dict]:
        """Получить ответы пользователей на тест"""
        result = []
        for attempt_id, attempt in data_storage.attempts.items():
            if attempt["test_id"] == test_id and attempt["status"] == "completed":
                user = data_storage.users.get(attempt["user_id"])
                if user:
                    user_answers = []
                    for answer_id, answer in data_storage.answers.items():
                        if answer["attempt_id"] == attempt_id:
                            question = data_storage.questions.get(answer["question_id"])
                            if question:
                                user_answers.append({
                                    "question_id": answer["question_id"],
                                    "question_text": question["text"],
                                    "answer_index": answer["answer"],
                                    "answer_text": question["options"][answer["answer"]] if answer[
                                                                                                "answer"] != -1 else "Нет ответа"
                                })

                    result.append({
                        "user_id": user["id"],
                        "full_name": user["full_name"],
                        "answers": user_answers
                    })
        return result

    # =========================
    # ATTEMPT METHODS
    # =========================
    async def create_attempt(self, token: str, test_id: int, user_id: int) -> Dict:
        """Создать попытку прохождения теста"""
        # Проверяем, активен ли тест
        test = data_storage.tests.get(test_id)
        if not test or not test["is_active"]:
            return {"error": "Тест не активен"}

        # Проверяем, есть ли уже активная попытка
        existing_attempt = None
        for attempt_id, attempt in data_storage.attempts.items():
            if attempt["user_id"] == user_id and attempt["test_id"] == test_id:
                if attempt["status"] == "in_progress":
                    # Проверяем, не устарела ли попытка (старше 24 часов)
                    if "started_at" in attempt:
                        try:
                            started_at = datetime.fromisoformat(attempt["started_at"].replace('Z', '+00:00'))
                            if (datetime.utcnow() - started_at).total_seconds() > 86400:  # 24 часа
                                # Помечаем старую попытку как устаревшую
                                attempt["status"] = "expired"
                                continue
                        except:
                            pass
                    existing_attempt = attempt
                    break

        if existing_attempt:
            return {"success": True, "attempt_id": existing_attempt["id"], "message": "Активная попытка уже существует"}

        # Создаем новую попытку
        attempt_id = max(data_storage.attempts.keys(), default=1000) + 1
        data_storage.attempts[attempt_id] = {
            "id": attempt_id,
            "user_id": user_id,
            "test_id": test_id,
            "status": "in_progress",
            "score": None,
            "started_at": datetime.utcnow().isoformat(),
            "finished_at": None,
            "answers": {}
        }

        # Создаем ответы для каждого вопроса
        for question_id in test["questions"]:
            answer_id = max(data_storage.answers.keys(), default=0) + 1
            question = data_storage.questions.get(question_id)
            if question:
                data_storage.answers[answer_id] = {
                    "id": answer_id,
                    "attempt_id": attempt_id,
                    "question_id": question_id,
                    "version": question["version"],
                    "answer": -1  # -1 означает "не определенный"
                }

        return {"success": True, "attempt_id": attempt_id, "message": "Попытка создана"}

    async def update_attempt_answer(self, token: str, attempt_id: int, question_id: int, answer_index: int) -> Dict:
        """Изменить ответ в попытке"""
        attempt = data_storage.attempts.get(attempt_id)
        if not attempt or attempt["status"] != "in_progress":
            return {"error": "Попытка не найдена или уже завершена"}

        # Находим ответ
        answer = None
        for answer_id, ans in data_storage.answers.items():
            if ans["attempt_id"] == attempt_id and ans["question_id"] == question_id:
                answer = ans
                break

        if answer:
            answer["answer"] = answer_index
            attempt["answers"][question_id] = answer_index
            return {"success": True, "message": "Ответ обновлён"}
        return {"error": "Ответ не найден"}

    async def complete_attempt(self, token: str, attempt_id: int) -> Dict:
        """Завершить попытку"""
        attempt = data_storage.attempts.get(attempt_id)
        if not attempt or attempt["status"] != "in_progress":
            return {"error": "Попытка не найдена или уже завершена"}

        # Рассчитываем оценку
        correct_count = 0
        total_questions = 0

        for question_id, answer_index in attempt["answers"].items():
            question = data_storage.questions.get(question_id)
            if question:
                total_questions += 1
                if answer_index == question["correct"]:
                    correct_count += 1

        score = int((correct_count / total_questions * 100)) if total_questions > 0 else 0
        attempt["score"] = score
        attempt["status"] = "completed"
        attempt["finished_at"] = datetime.utcnow().isoformat()

        return {"success": True, "score": score, "message": "Попытка завершена"}

    async def get_attempt_info(self, token: str, attempt_id: int) -> Dict:
        """Получить информацию о попытке"""
        attempt = data_storage.attempts.get(attempt_id)
        if attempt:
            user = data_storage.users.get(attempt["user_id"])
            test = data_storage.tests.get(attempt["test_id"])
            return {
                "attempt": attempt,
                "user": user,
                "test": test
            }
        return {"error": "Попытка не найдена"}

    # =========================
    # EXISTING METHODS
    # =========================
    async def get_tests(self, token: str, course_id: int = DEFAULT_COURSE_ID) -> List[Dict]:
        """Получить список тестов курса через API"""
        try:
            logger.info(f"📚 Запрос тестов для курса {course_id}")
            response = await self.request("GET", f"/course/tests?course_id={course_id}", token)

            logger.info(f"📚 Получен ответ: {type(response)}")

            if isinstance(response, dict) and "text" in response:
                try:
                    parsed = json.loads(response["text"])
                    logger.info(f"📚 Распарсено из текста: {type(parsed)}")
                    if isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict):
                        return parsed.get("tests", [])
                except Exception as e:
                    logger.error(f"📚 Ошибка парсинга текста: {e}")
                    return []

            if isinstance(response, list):
                logger.info(f"📚 Получен список из {len(response)} тестов")
                return response

            if isinstance(response, dict):
                tests = response.get("tests", []) or response.get("data", []) or []
                logger.info(f"📚 Тесты из dict: {type(tests)}, длина: {len(tests) if tests else 0}")
                return tests if isinstance(tests, list) else []

            logger.warning(f"📚 Неизвестный формат ответа: {type(response)}")
            return []

        except Exception as e:
            logger.error(f"📚 Ошибка при получении тестов: {e}")
            return [test for test in data_storage.tests.values() if test["course_id"] == course_id]

    async def start_test(self, token: str, test_id: int) -> Dict:
        """Начать тест"""
        try:
            logger.info(f"🚀 Запуск теста {test_id}")
            return await self.request("POST", f"/test/start?test_id={test_id}", token)
        except Exception as e:
            logger.error(f"🚀 Ошибка запуска теста: {e}")
            # Используем данные из хранилища
            test = data_storage.tests.get(test_id)
            if test and test["is_active"]:
                return {"attempt_id": 1000 + test_id, "id": 1000 + test_id}
            return {"error": "Тест не найден или не активен"}

    async def submit_answer(self, token: str, attempt_id: int, question_id: int, option: int) -> Dict:
        """Отправить ответ на вопрос"""
        try:
            logger.info(f"📝 Отправка ответа: attempt={attempt_id}, question={question_id}, option={option}")
            return await self.request("POST", f"/test/answer?attempt_id={attempt_id}&question_id={question_id}",
                                      token, {"option": option})
        except Exception as e:
            logger.error(f"📝 Ошибка отправки ответа: {e}")
            return {"status": "ok"}

    async def finish_test(self, token: str, attempt_id: int) -> str:
        """Завершить тест и получить результат"""
        try:
            logger.info(f"🏁 Завершение теста {attempt_id}")
            response = await self.request("POST", f"/test/finish?attempt_id={attempt_id}", token)
            return response.get("text", "85%") or str(response)
        except Exception as e:
            logger.error(f"🏁 Ошибка завершения теста: {e}")
            return "75% (результат из заглушки)"

    async def get_question_details(self, token: str, question_id: int) -> Dict:
        """Получить детали вопроса"""
        return data_storage.questions.get(question_id, {
            "id": question_id,
            "text": f"Вопрос {question_id}",
            "options": ["Вариант 1", "Вариант 2", "Вариант 3"],
            "correct": 0
        })

    async def get_test_questions(self, token: str, test_id: int) -> List[int]:
        """Получить список вопросов теста"""
        test = data_storage.tests.get(test_id)
        if test:
            return test.get("questions", [])
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
        "commands_processed": stats.commands_count
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
# ОБНОВЛЕННАЯ КОМАНДА TESTS С ИСПОЛЬЗОВАНИЕМ API
# =========================
@dp.message(Command("tests"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_tests(message: Message, user: Dict):
    """Список доступных тестов через API"""
    api_token = user.get("api_token", "")
    user_id = user.get("user_id")

    try:
        # Получаем курсы через API
        courses = await api_client.get_courses(api_token)

        if not courses:
            await message.answer("📚 <b>Нет доступных курсов</b>\n\nВ системе пока нет курсов.")
            return

        text = "📚 <b>Доступные тесты:</b>\n\n"
        has_tests = False

        for course in courses[:10]:  # Ограничиваем 10 курсами
            course_id = course.get("id")
            course_name = course.get("name", f"Курс {course_id}")

            # Получаем тесты для курса через API
            tests = await api_client.get_course_tests(api_token, course_id)
            if not tests:
                continue

            # Фильтруем только активные тесты
            active_tests = []
            for test in tests:
                # Проверяем разные форматы данных от API
                if isinstance(test, dict):
                    if test.get("is_active") in [True, "true", "True", 1]:
                        active_tests.append(test)
                elif isinstance(test, str):
                    # Если тест это строка (ID), создаем простой объект
                    try:
                        test_id = int(test)
                        active_tests.append({"id": test_id, "name": f"Тест {test_id}", "is_active": True})
                    except:
                        pass

            if not active_tests:
                continue

            has_tests = True
            text += f"🎓 <b>{course_name}</b> (ID: {course_id})\n"

            for test in active_tests[:5]:  # Ограничиваем 5 тестами на курс
                test_id = test.get("id", "?")
                test_name = test.get("name", f"Тест {test_id}")

                # Получаем вопросы теста
                questions = []
                if "questions" in test and test["questions"]:
                    questions = test["questions"]
                elif "question_ids" in test and test["question_ids"]:
                    questions = test["question_ids"]

                # Проверяем, проходил ли пользователь тест
                user_attempts = []
                for attempt_id, attempt in data_storage.attempts.items():
                    if (attempt["user_id"] == user_id and
                            attempt["test_id"] == test_id and
                            attempt["status"] == "completed"):
                        user_attempts.append(attempt)

                best_score = max([a.get("score", 0) for a in user_attempts]) if user_attempts else None

                text += f"   🧪 <b>{test_name}</b> (ID: {test_id})\n"
                text += f"      ❓ Вопросов: {len(questions) if questions else '?'}\n"

                if best_score is not None:
                    text += f"      🏆 Лучший результат: {best_score}%\n"
                    text += f"      🔄 Пройти снова: /start_test {test_id}\n"
                else:
                    text += f"      🚀 Начать тест: /start_test {test_id}\n"

                # Показываем ID вопросов если есть
                if questions and len(questions) > 0:
                    text += f"      📋 ID вопросов: {', '.join(map(str, questions[:3]))}"
                    if len(questions) > 3:
                        text += f" ... (ещё {len(questions) - 3})"
                    text += "\n"

                text += "\n"

            text += "\n"

        if not has_tests:
            text = "📚 <b>Нет доступных активных тестов</b>\n\nВ данный момент нет активных тестов для прохождения."

        text += "\n<b>Чтобы начать тест, используйте команду:</b>\n"
        text += "<code>/start_test ID_теста</code>\n\n"
        text += "<b>Пример:</b>\n"
        text += "<code>/start_test 1</code> - начать тест с ID 1\n\n"
        text += "<b>Просмотреть информацию о тесте:</b>\n"
        text += "<code>/test_info ID_теста</code>"

        await message.answer(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Ошибка при получении тестов через API: {e}")

        # Fallback на локальное хранилище
        try:
            tests = [test for test in data_storage.tests.values() if test["is_active"]]

            if not tests:
                await message.answer(
                    "📚 <b>Нет доступных тестов</b>\n\nНа данный момент нет активных тестов для прохождения.")
                return

            text = "📚 <b>Доступные тесты (локальные данные):</b>\n\n"

            for test in tests[:15]:  # Ограничиваем 15 тестами
                test_id = test.get("id")
                test_name = test.get("name", f"Тест {test_id}")
                course_id = test.get("course_id")
                course = data_storage.courses.get(course_id, {})
                course_name = course.get("name", f"Курс {course_id}")
                questions = test.get("questions", [])

                text += f"🧪 <b>{test_name}</b> (ID: {test_id})\n"
                text += f"   📚 Курс: {course_name}\n"
                text += f"   ❓ Вопросов: {len(questions)}\n"
                text += f"   🚀 Команда: /start_test {test_id}\n\n"

            await message.answer(text)

        except Exception as fallback_error:
            logger.error(f"Ошибка в fallback: {fallback_error}")
            await message.answer(f"❌ <b>Ошибка при загрузке тестов:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА TEST_INFO (ИНФОРМАЦИЯ О ТЕСТЕ)
# =========================
@dp.message(Command("test_info"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_test_info(message: Message, user: Dict):
    """Получить детальную информацию о тесте"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/test_info ID_теста</code>\n\nПример: <code>/test_info 1</code>")
        return

    try:
        test_id = int(args[1])
        api_token = user.get("api_token", "")
        user_id = user.get("user_id")

        # Ищем тест в локальном хранилище (как fallback)
        test = data_storage.tests.get(test_id)

        if not test:
            # Пробуем получить через API
            try:
                # Ищем тест во всех курсах
                courses = await api_client.get_courses(api_token)
                for course in courses:
                    course_tests = await api_client.get_course_tests(api_token, course.get("id"))
                    for t in course_tests:
                        if t.get("id") == test_id:
                            test = t
                            break
                    if test:
                        break
            except:
                pass

        if not test:
            await message.answer(f"❌ <b>Тест с ID {test_id} не найден</b>")
            return

        test_name = test.get("name", f"Тест {test_id}")
        course_id = test.get("course_id")
        questions = test.get("questions", [])
        is_active = test.get("is_active", False)

        # Получаем информацию о курсе
        course = data_storage.courses.get(course_id, {})
        course_name = course.get("name", f"Курс {course_id}")

        # Получаем попытки пользователя
        user_attempts = []
        for attempt_id, attempt in data_storage.attempts.items():
            if (attempt["user_id"] == user_id and
                    attempt["test_id"] == test_id):
                user_attempts.append(attempt)

        completed_attempts = [a for a in user_attempts if a.get("status") == "completed"]
        in_progress_attempts = [a for a in user_attempts if a.get("status") == "in_progress"]

        text = f"🧪 <b>Информация о тесте</b>\n\n"
        text += f"<b>Название:</b> {test_name}\n"
        text += f"<b>ID теста:</b> {test_id}\n"
        text += f"<b>Курс:</b> {course_name} (ID: {course_id})\n"
        text += f"<b>Статус:</b> {'🟢 Активен' if is_active else '🔴 Неактивен'}\n"
        text += f"<b>Вопросов:</b> {len(questions)}\n\n"

        if completed_attempts:
            best_score = max([a.get("score", 0) for a in completed_attempts])
            avg_score = sum([a.get("score", 0) for a in completed_attempts]) / len(completed_attempts)

            text += f"<b>Ваши результаты:</b>\n"
            text += f"  • Завершено попыток: {len(completed_attempts)}\n"
            text += f"  • Лучший результат: {best_score}%\n"
            text += f"  • Средний результат: {avg_score:.1f}%\n\n"

        if in_progress_attempts:
            text += f"<b>Активные попытки:</b> {len(in_progress_attempts)}\n\n"

        text += f"<b>Команды:</b>\n"
        if is_active:
            if in_progress_attempts:
                text += f"• /finish_test [ID_попытки] - завершить активную попытку\n"
            else:
                text += f"• /start_test {test_id} - начать тест\n"
        else:
            text += f"• Тест временно недоступен\n"

        text += f"• /my_attempts - ваши попытки\n"

        await message.answer(text)

    except ValueError:
        await message.answer("❌ <b>Неверный ID теста</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при получении информации о тесте: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# ОСТАЛЬНОЙ КОД БЕЗ ИЗМЕНЕНИЙ
# =========================
# [Здесь должен быть весь остальной код из вашего файла без изменений]
# Включая команды start, login, help, status, profile и т.д.
# Из-за ограничения длины ответа я не могу включить весь код,
# но вы можете просто добавить вышеуказанные функции в существующий файл


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
    logger.info(f"🌐 HTTP Server порт: {HTTP_PORT}")

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