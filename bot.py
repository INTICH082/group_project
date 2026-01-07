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
HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))

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
# DATA STORAGE (ЗАГЛУШКИ ДЛЯ ТЕСТОВЫХ ДАННЫХ)
# =========================
class DataStorage:
    def __init__(self):
        # Заглушки данных
        self.users = {
            1: {"id": 1, "full_name": "Иванов Иван Иванович", "email": "teacher@example.com", "role": "teacher",
                "is_blocked": False},
            2: {"id": 2, "full_name": "Петров Петр Петрович", "email": "student1@example.com", "role": "student",
                "is_blocked": False},
            3: {"id": 3, "full_name": "Сидорова Анна Владимировна", "email": "student2@example.com", "role": "student",
                "is_blocked": False},
        }

        self.courses = {
            1: {"id": 1, "name": "Программирование на Python", "description": "Основы программирования на Python",
                "teacher_id": 1, "is_active": True},
            2: {"id": 2, "name": "Базы данных", "description": "Основы работы с базами данных", "teacher_id": 1,
                "is_active": True},
            3: {"id": 3, "name": "Веб-разработка", "description": "Создание веб-приложений", "teacher_id": 1,
                "is_active": True},
        }

        self.course_students = {
            1: [2, 3],  # Python: student1, student2
            2: [2],  # Базы данных: student1
        }

        self.tests = {
            1: {"id": 1, "name": "Тест по основам Python", "course_id": 1, "is_active": True, "questions": [1, 2, 3]},
            2: {"id": 2, "name": "Тест по функциям Python", "course_id": 1, "is_active": False, "questions": [4, 5]},
            3: {"id": 3, "name": "Тест по SQL", "course_id": 2, "is_active": True, "questions": [6, 7]},
        }

        self.questions = {
            1: {"id": 1, "title": "Типы данных Python", "text": "Что такое Python?",
                "options": ["Язык программирования", "Змея", "Оба варианта верны"], "correct": 2, "author_id": 1,
                "version": 1},
            2: {"id": 2, "title": "Списки Python", "text": "Как создать пустой список в Python?",
                "options": ["list()", "[]", "Оба варианта верны"], "correct": 2, "author_id": 1, "version": 1},
            3: {"id": 3, "title": "Функции Python", "text": "Что такое функция в Python?",
                "options": ["Блок кода", "Ключевое слово", "Именованный блок кода"], "correct": 2, "author_id": 1,
                "version": 1},
            4: {"id": 4, "title": "Аргументы функций", "text": "Что такое args в Python?",
                "options": ["Позиционные аргументы", "Именованные аргументы", "Ключевое слово"], "correct": 0,
                "author_id": 1, "version": 1},
            5: {"id": 5, "title": "Декораторы", "text": "Что такое декоратор в Python?",
                "options": ["Функция", "Класс", "Функция высшего порядка"], "correct": 2, "author_id": 1, "version": 1},
            6: {"id": 6, "title": "SQL SELECT", "text": "Как выбрать все данные из таблицы?",
                "options": ["SELECT * FROM table", "GET * FROM table", "FIND * FROM table"], "correct": 0,
                "author_id": 1, "version": 1},
            7: {"id": 7, "title": "SQL JOIN", "text": "Что такое JOIN в SQL?",
                "options": ["Объединение таблиц", "Удаление данных", "Создание таблиц"], "correct": 0, "author_id": 1,
                "version": 1},
        }

        self.attempts = {
            1001: {"id": 1001, "user_id": 2, "test_id": 1, "status": "completed", "score": 85,
                   "answers": {1: 2, 2: 2, 3: 2}},
            1002: {"id": 1002, "user_id": 3, "test_id": 1, "status": "completed", "score": 70,
                   "answers": {1: 2, 2: 0, 3: 1}},
            1003: {"id": 1003, "user_id": 2, "test_id": 3, "status": "in_progress", "score": None, "answers": {6: 0}},
        }

        self.answers = {
            1: {"id": 1, "attempt_id": 1001, "question_id": 1, "version": 1, "answer": 2},
            2: {"id": 2, "attempt_id": 1001, "question_id": 2, "version": 1, "answer": 2},
            3: {"id": 3, "attempt_id": 1001, "question_id": 3, "version": 1, "answer": 2},
            4: {"id": 4, "attempt_id": 1002, "question_id": 1, "version": 1, "answer": 2},
            5: {"id": 5, "attempt_id": 1002, "question_id": 2, "version": 1, "answer": 0},
            6: {"id": 6, "attempt_id": 1002, "question_id": 3, "version": 1, "answer": 1},
            7: {"id": 7, "attempt_id": 1003, "question_id": 6, "version": 1, "answer": 0},
        }


data_storage = DataStorage()


# =========================
# API CLIENT - УЛУЧШЕННАЯ ВЕРСИЯ
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
            else:  # student
                permissions = [
                    Permission.USER_DATA_READ,  # о себе
                    Permission.COURSE_TESTLIST,  # тесты курсов, на которые записан
                    Permission.COURSE_TEST_READ,  # просмотр тестов
                    Permission.ANSWER_READ,  # просмотр своих ответов
                    Permission.ANSWER_UPDATE,  # изменение своих ответов
                    Permission.ANSWER_DEL,  # удаление своих ответов
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
            if attempt["user_id"] == user_id and attempt["test_id"] == test_id and attempt["status"] == "in_progress":
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
    # EXISTING METHODS (ОСТАВЛЯЕМ БЕЗ ИЗМЕНЕНИЙ)
    # =========================
    async def get_tests(self, token: str, course_id: int = DEFAULT_COURSE_ID) -> List[Dict]:
        """Получить список тестов курса"""
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
    token = api_client.generate_token(user_id, role)
    permissions = json.loads(jwt.decode(token, JWT_SECRET, algorithms=["HS256"])).get("permissions", [])

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
# ОБНОВЛЕННАЯ КОМАНДА START С ВЫБОРОМ РОЛИ
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
            [InlineKeyboardButton(text="🔐 Авторизоваться", callback_data="login")],
            [InlineKeyboardButton(text="👨‍🎓 Войти как студент", callback_data="quick_student")],
            [InlineKeyboardButton(text="👨‍🏫 Войти как преподаватель", callback_data="quick_teacher")]
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
        else:
            provider_name = "GitHub" if provider == "github" else "Яндекс ID"
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
/profile — ваш профиль
/logout — выход из системы

Используйте /help для полного списка команд.
"""
        kb = None

    await message.answer(text, reply_markup=kb)


# =========================
# БЫСТРАЯ АВТОРИЗАЦИЯ ЧЕРЕЗ КНОПКИ
# =========================
@dp.callback_query(F.data == "quick_student")
async def callback_quick_student(callback: CallbackQuery):
    """Быстрая авторизация как студент"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    # Создаем тестовые данные для авторизации студента
    user_id = 2
    email = f"student_{chat_id}@test.com"

    await set_user_authorized(chat_id, user_id, email, "student")

    await callback.answer("✅ Авторизация студента успешна!")
    await callback.message.edit_text(
        f"✅ <b>Авторизация студента успешна!</b>\n\nДобро пожаловать, {email}\n\nВы можете проходить тесты.",
        reply_markup=None
    )


@dp.callback_query(F.data == "quick_teacher")
async def callback_quick_teacher(callback: CallbackQuery):
    """Быстрая авторизация как преподаватель"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    # Создаем тестовые данные для авторизации преподавателя
    user_id = 1
    email = f"teacher_{chat_id}@test.com"

    await set_user_authorized(chat_id, user_id, email, "teacher")

    await callback.answer("✅ Авторизация преподавателя успешна!")
    await callback.message.edit_text(
        f"✅ <b>Авторизация преподавателя успешна!</b>\n\nДобро пожаловать, {email}\n\nВы можете управлять системой.",
        reply_markup=None
    )


# =========================
# ОБНОВЛЕННАЯ КОМАНДА LOGIN С ВЫБОРОМ РОЛИ
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

    text = """
🔐 <b>Выберите роль для входа:</b>

1. <b>👨‍🎓 Студент</b> — доступ к прохождению тестов
2. <b>👨‍🏫 Преподаватель</b> — доступ к управлению системой

Или выберите способ авторизации:
"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🎓 Студент", callback_data="role_student")],
        [InlineKeyboardButton(text="👨‍🏫 Преподаватель", callback_data="role_teacher")],
        [InlineKeyboardButton(text="🔢 Авторизация через код", callback_data="login_code")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "role_student")
async def callback_role_student(callback: CallbackQuery):
    """Выбор роли студента"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    text = """
👨‍🎓 <b>Авторизация как студент</b>

Выберите способ авторизации:
"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔢 Авторизация через код", callback_data="login_code_student")],
        [InlineKeyboardButton(text="🚀 Быстрая авторизация", callback_data="quick_student")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "role_teacher")
async def callback_role_teacher(callback: CallbackQuery):
    """Выбор роли преподавателя"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    text = """
👨‍🏫 <b>Авторизация как преподаватель</b>

Выберите способ авторизации:
"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔢 Авторизация через код", callback_data="login_code_teacher")],
        [InlineKeyboardButton(text="🚀 Быстрая авторизация", callback_data="quick_teacher")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# =========================
# КОМАНДЫ ДЛЯ СТУДЕНТА
# =========================
@dp.message(Command("my_courses"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_my_courses(message: Message, user: Dict):
    """Просмотр курсов, на которые записан студент"""
    chat_id = message.chat.id
    api_token = user.get("api_token", "")
    user_id = user.get("user_id")

    try:
        user_data = await api_client.get_user_courses_grades(api_token, user_id)
        courses = user_data.get("courses", [])

        if not courses:
            await message.answer("📚 <b>Вы не записаны ни на один курс</b>")
            return

        text = "📚 <b>Мои курсы</b>\n\n"
        for course in courses:
            text += f"🔸 <b>{course['name']}</b> (ID: {course['id']})\n"
            text += f"   Описание: {course['description']}\n\n"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении курсов: {e}")
        await message.answer("❌ <b>Ошибка при загрузке курсов</b>")


@dp.message(Command("my_grades"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_my_grades(message: Message, user: Dict):
    """Просмотр своих оценок"""
    chat_id = message.chat.id
    api_token = user.get("api_token", "")
    user_id = user.get("user_id")

    try:
        user_data = await api_client.get_user_courses_grades(api_token, user_id)
        attempts = user_data.get("attempts", [])

        if not attempts:
            await message.answer("📊 <b>У вас пока нет оценок</b>")
            return

        text = "📊 <b>Мои оценки</b>\n\n"
        for attempt in attempts:
            if attempt["status"] == "completed" and attempt["score"] is not None:
                test = data_storage.tests.get(attempt["test_id"])
                test_name = test["name"] if test else f"Тест {attempt['test_id']}"
                text += f"📝 <b>{test_name}</b>\n"
                text += f"   Оценка: {attempt['score']}%\n"
                text += f"   Статус: Завершён\n\n"
            elif attempt["status"] == "in_progress":
                test = data_storage.tests.get(attempt["test_id"])
                test_name = test["name"] if test else f"Тест {attempt['test_id']}"
                text += f"📝 <b>{test_name}</b>\n"
                text += f"   Статус: В процессе\n\n"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении оценок: {e}")
        await message.answer("❌ <b>Ошибка при загрузке оценок</b>")


@dp.message(Command("my_attempts"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_my_attempts(message: Message, user: Dict):
    """Просмотр своих попыток"""
    chat_id = message.chat.id
    api_token = user.get("api_token", "")
    user_id = user.get("user_id")

    try:
        user_data = await api_client.get_user_courses_grades(api_token, user_id)
        attempts = user_data.get("attempts", [])

        if not attempts:
            await message.answer("📝 <b>У вас пока нет попыток</b>")
            return

        text = "📝 <b>Мои попытки</b>\n\n"
        for attempt in attempts:
            test = data_storage.tests.get(attempt["test_id"])
            test_name = test["name"] if test else f"Тест {attempt['test_id']}"

            text += f"🧪 <b>{test_name}</b>\n"
            text += f"   ID попытки: {attempt['id']}\n"
            text += f"   Статус: {attempt['status']}\n"
            if attempt["score"] is not None:
                text += f"   Оценка: {attempt['score']}%\n"
            text += "\n"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении попыток: {e}")
        await message.answer("❌ <b>Ошибка при загрузке попыток</b>")


# =========================
# КОМАНДЫ ДЛЯ ПРЕПОДАВАТЕЛЯ - ПОЛЬЗОВАТЕЛИ
# =========================
@dp.message(Command("users"))
@rate_limit()
@require_auth()
@require_permission(Permission.USER_LIST_READ)
@safe_send_message
async def cmd_users(message: Message, user: Dict):
    """Просмотр списка пользователей"""
    api_token = user.get("api_token", "")

    try:
        users = await api_client.get_users(api_token)

        if not users:
            await message.answer("👥 <b>Пользователи не найдены</b>")
            return

        text = "👥 <b>Список пользователей</b>\n\n"
        for user_data in users:
            role_emoji = "👨‍🏫" if user_data["role"] == "teacher" else "👨‍🎓"
            blocked = "🔴" if user_data.get("is_blocked") else "🟢"

            text += f"{role_emoji} {blocked} <b>{user_data['full_name']}</b>\n"
            text += f"   ID: {user_data['id']}\n"
            text += f"   Email: {user_data['email']}\n"
            text += f"   Роль: {user_data['role']}\n\n"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении пользователей: {e}")
        await message.answer("❌ <b>Ошибка при загрузке пользователей</b>")


@dp.message(Command("user_info"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_user_info(message: Message, user: Dict):
    """Просмотр информации о пользователе"""
    api_token = user.get("api_token", "")

    # Извлекаем ID пользователя из команды
    parts = message.text.split()
    if len(parts) < 2:
        # Если ID не указан, показываем информацию о себе
        user_id = user.get("user_id")
    else:
        try:
            user_id = int(parts[1])
        except ValueError:
            await message.answer("❌ <b>ID пользователя должен быть числом</b>")
            return

    try:
        user_info = await api_client.get_user_info(api_token, user_id)

        if not user_info:
            await message.answer("❌ <b>Пользователь не найден</b>")
            return

        role_emoji = "👨‍🏫" if user_info["role"] == "teacher" else "👨‍🎓"
        blocked = "🔴 Заблокирован" if user_info.get("is_blocked") else "🟢 Активен"

        text = f"{role_emoji} <b>Информация о пользователе</b>\n\n"
        text += f"👤 <b>ФИО:</b> {user_info['full_name']}\n"
        text += f"🔑 <b>ID:</b> {user_info['id']}\n"
        text += f"📧 <b>Email:</b> {user_info['email']}\n"
        text += f"🎭 <b>Роль:</b> {user_info['role']}\n"
        text += f"🔒 <b>Статус:</b> {blocked}\n"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пользователе: {e}")
        await message.answer("❌ <b>Ошибка при загрузке информации</b>")


@dp.message(Command("update_fullname"))
@rate_limit()
@require_auth()
@require_permission(Permission.USER_FULLNAME_WRITE)
@safe_send_message
async def cmd_update_fullname(message: Message, user: Dict):
    """Изменение ФИО пользователя"""
    api_token = user.get("api_token", "")

    # Извлекаем ID пользователя и новое ФИО из команды
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ <b>Использование:</b> /update_fullname ID_пользователя Новое_ФИО")
        return

    try:
        user_id = int(parts[1])
        new_fullname = parts[2]

        result = await api_client.update_user_fullname(api_token, user_id, new_fullname)

        if result.get("success"):
            await message.answer(f"✅ <b>ФИО пользователя обновлено</b>")
        else:
            await message.answer(f"❌ <b>Ошибка:</b> {result.get('error', 'Неизвестная ошибка')}")
    except ValueError:
        await message.answer("❌ <b>ID пользователя должен быть числом</b>")
    except Exception as e:
        logger.error(f"Ошибка при обновлении ФИО: {e}")
        await message.answer("❌ <b>Ошибка при обновлении ФИО</b>")


@dp.message(Command("user_roles"))
@rate_limit()
@require_auth()
@require_permission(Permission.USER_ROLES_READ)
@safe_send_message
async def cmd_user_roles(message: Message, user: Dict):
    """Просмотр ролей пользователя"""
    api_token = user.get("api_token", "")

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ <b>Использование:</b> /user_roles ID_пользователя")
        return

    try:
        user_id = int(parts[1])
        roles = await api_client.get_user_roles(api_token, user_id)

        if roles:
            text = f"🎭 <b>Роли пользователя ID {user_id}</b>\n\n"
            text += "\n".join([f"• {role}" for role in roles])
            await message.answer(text)
        else:
            await message.answer("❌ <b>Пользователь не найден</b>")
    except ValueError:
        await message.answer("❌ <b>ID пользователя должен быть числом</b>")
    except Exception as e:
        logger.error(f"Ошибка при получении ролей: {e}")
        await message.answer("❌ <b>Ошибка при загрузке ролей</b>")


@dp.message(Command("block_user"))
@rate_limit()
@require_auth()
@require_permission(Permission.USER_BLOCK_WRITE)
@require_role("teacher")
@safe_send_message
async def cmd_block_user(message: Message, user: Dict):
    """Блокировка/разблокировка пользователя"""
    api_token = user.get("api_token", "")

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ <b>Использование:</b> /block_user ID_пользователя true/false")
        return

    try:
        user_id = int(parts[1])
        block_status = parts[2].lower() == "true"

        result = await api_client.update_user_block_status(api_token, user_id, block_status)

        if result.get("success"):
            action = "заблокирован" if block_status else "разблокирован"
            await message.answer(f"✅ <b>Пользователь {action}</b>")
        else:
            await message.answer(f"❌ <b>Ошибка:</b> {result.get('error', 'Неизвестная ошибка')}")
    except ValueError:
        await message.answer("❌ <b>ID пользователя должен быть числом</b>")
    except Exception as e:
        logger.error(f"Ошибка при блокировке пользователя: {e}")
        await message.answer("❌ <b>Ошибка при блокировке пользователя</b>")


# =========================
# КОМАНДЫ ДЛЯ ПРЕПОДАВАТЕЛЯ - КУРСЫ
# =========================
@dp.message(Command("all_courses"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_all_courses(message: Message, user: Dict):
    """Просмотр всех курсов"""
    api_token = user.get("api_token", "")

    try:
        courses = await api_client.get_courses(api_token)

        if not courses:
            await message.answer("📚 <b>Курсы не найдены</b>")
            return

        text = "📚 <b>Все курсы</b>\n\n"
        for course in courses:
            teacher = data_storage.users.get(course["teacher_id"], {})
            teacher_name = teacher.get("full_name", f"Преподаватель {course['teacher_id']}")
            status = "🟢" if course.get("is_active", True) else "🔴"

            text += f"{status} <b>{course['name']}</b> (ID: {course['id']})\n"
            text += f"   Описание: {course['description']}\n"
            text += f"   Преподаватель: {teacher_name}\n\n"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении курсов: {e}")
        await message.answer("❌ <b>Ошибка при загрузке курсов</b>")


@dp.message(Command("create_course"))
@rate_limit()
@require_auth()
@require_permission(Permission.COURSE_ADD)
@require_role("teacher")
@safe_send_message
async def cmd_create_course(message: Message, user: Dict):
    """Создание нового курса"""
    api_token = user.get("api_token", "")
    user_id = user.get("user_id")

    # Формат: /create_course Название; Описание
    parts = message.text.split(';', 1)
    if len(parts) < 2:
        await message.answer("❌ <b>Использование:</b> /create_course Название; Описание")
        return

    name = parts[0].strip().replace('/create_course ', '')
    description = parts[1].strip()

    try:
        result = await api_client.create_course(api_token, name, description, user_id)

        if result.get("success"):
            await message.answer(f"✅ <b>Курс создан</b>\n\nID курса: {result['course_id']}\nНазвание: {name}")
        else:
            await message.answer(f"❌ <b>Ошибка:</b> {result.get('error', 'Неизвестная ошибка')}")
    except Exception as e:
        logger.error(f"Ошибка при создании курса: {e}")
        await message.answer("❌ <b>Ошибка при создании курса</b>")


@dp.message(Command("course_info"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_course_info(message: Message, user: Dict):
    """Просмотр информации о курсе"""
    api_token = user.get("api_token", "")

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ <b>Использование:</b> /course_info ID_курса")
        return

    try:
        course_id = int(parts[1])
        course_info = await api_client.get_course_info(api_token, course_id)

        if course_info and not course_info.get("error"):
            teacher = course_info.get("teacher", {})
            teacher_name = teacher.get("full_name", f"Преподаватель {course_info['teacher_id']}")
            status = "🟢 Активен" if course_info.get("is_active", True) else "🔴 Не активен"

            text = f"📚 <b>Информация о курсе</b>\n\n"
            text += f"🏫 <b>Название:</b> {course_info['name']}\n"
            text += f"🔑 <b>ID:</b> {course_info['id']}\n"
            text += f"📝 <b>Описание:</b> {course_info['description']}\n"
            text += f"👨‍🏫 <b>Преподаватель:</b> {teacher_name}\n"
            text += f"🔒 <b>Статус:</b> {status}\n"

            # Показываем тесты курса
            tests = await api_client.get_course_tests(api_token, course_id)
            if tests:
                text += f"\n📋 <b>Тесты курса ({len(tests)}):</b>\n"
                for test in tests:
                    status = "🟢" if test["is_active"] else "🔴"
                    text += f"  {status} {test['name']} (ID: {test['id']})\n"

            await message.answer(text)
        else:
            await message.answer("❌ <b>Курс не найден</b>")
    except ValueError:
        await message.answer("❌ <b>ID курса должен быть числом</b>")
    except Exception as e:
        logger.error(f"Ошибка при получении информации о курсе: {e}")
        await message.answer("❌ <b>Ошибка при загрузке информации о курсе</b>")


@dp.message(Command("course_students"))
@rate_limit()
@require_auth()
@require_permission(Permission.COURSE_USERLIST)
@require_role("teacher")
@safe_send_message
async def cmd_course_students(message: Message, user: Dict):
    """Просмотр студентов курса"""
    api_token = user.get("api_token", "")

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ <b>Использование:</b> /course_students ID_курса")
        return

    try:
        course_id = int(parts[1])
        students = await api_client.get_course_students(api_token, course_id)

        if not students:
            await message.answer(f"👥 <b>На курсе ID {course_id} нет студентов</b>")
            return

        text = f"👥 <b>Студенты курса ID {course_id}</b>\n\n"
        for student in students:
            blocked = "🔴" if student.get("is_blocked") else "🟢"
            text += f"{blocked} <b>{student['full_name']}</b>\n"
            text += f"   ID: {student['id']}\n"
            text += f"   Email: {student['email']}\n\n"

        await message.answer(text)
    except ValueError:
        await message.answer("❌ <b>ID курса должен быть числом</b>")
    except Exception as e:
        logger.error(f"Ошибка при получении студентов курса: {e}")
        await message.answer("❌ <b>Ошибка при загрузке студентов курса</b>")


@dp.message(Command("enroll_student"))
@rate_limit()
@require_auth()
@require_permission(Permission.COURSE_USER_ADD)
@safe_send_message
async def cmd_enroll_student(message: Message, user: Dict):
    """Запись студента на курс"""
    api_token = user.get("api_token", "")

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ <b>Использование:</b> /enroll_student ID_курса ID_студента")
        return

    try:
        course_id = int(parts[1])
        student_id = int(parts[2])

        result = await api_client.enroll_student_to_course(api_token, course_id, student_id)

        if result.get("success"):
            await message.answer(f"✅ <b>Студент записан на курс</b>")
        else:
            await message.answer(f"❌ <b>Ошибка:</b> {result.get('error', 'Неизвестная ошибка')}")
    except ValueError:
        await message.answer("❌ <b>ID курса и ID студента должны быть числами</b>")
    except Exception as e:
        logger.error(f"Ошибка при записи студента на курс: {e}")
        await message.answer("❌ <b>Ошибка при записи студента на курс</b>")


# =========================
# КОМАНДЫ ДЛЯ ПРЕПОДАВАТЕЛЯ - ТЕСТЫ
# =========================
@dp.message(Command("course_tests"))
@rate_limit()
@require_auth()
@require_permission(Permission.COURSE_TESTLIST)
@safe_send_message
async def cmd_course_tests(message: Message, user: Dict):
    """Просмотр тестов курса"""
    api_token = user.get("api_token", "")

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ <b>Использование:</b> /course_tests ID_курса")
        return

    try:
        course_id = int(parts[1])
        tests = await api_client.get_course_tests(api_token, course_id)

        if not tests:
            await message.answer(f"📋 <b>В курсе ID {course_id} нет тестов</b>")
            return

        course_info = await api_client.get_course_info(api_token, course_id)
        course_name = course_info.get("name", f"Курс {course_id}") if course_info else f"Курс {course_id}"

        text = f"📋 <b>Тесты курса: {course_name}</b>\n\n"
        for test in tests:
            status = "🟢 Активен" if test["is_active"] else "🔴 Не активен"
            text += f"🧪 <b>{test['name']}</b> (ID: {test['id']})\n"
            text += f"   Статус: {status}\n"
            text += f"   Вопросов: {len(test.get('questions', []))}\n\n"

        await message.answer(text)
    except ValueError:
        await message.answer("❌ <b>ID курса должен быть числом</b>")
    except Exception as e:
        logger.error(f"Ошибка при получении тестов курса: {e}")
        await message.answer("❌ <b>Ошибка при загрузке тестов курса</b>")


@dp.message(Command("add_test"))
@rate_limit()
@require_auth()
@require_permission(Permission.COURSE_TEST_ADD)
@require_role("teacher")
@safe_send_message
async def cmd_add_test(message: Message, user: Dict):
    """Добавление теста в курс"""
    api_token = user.get("api_token", "")

    # Формат: /add_test ID_курса; Название_теста
    parts = message.text.split(';', 1)
    if len(parts) < 2:
        await message.answer("❌ <b>Использование:</b> /add_test ID_курса; Название_теста")
        return

    try:
        course_id = int(parts[0].strip().replace('/add_test ', ''))
        test_name = parts[1].strip()

        result = await api_client.add_test_to_course(api_token, course_id, test_name)

        if result.get("success"):
            await message.answer(
                f"✅ <b>Тест добавлен в курс</b>\n\nID теста: {result['test_id']}\nНазвание: {test_name}")
        else:
            await message.answer(f"❌ <b>Ошибка:</b> {result.get('error', 'Неизвестная ошибка')}")
    except ValueError:
        await message.answer("❌ <b>ID курса должен быть числом</b>")
    except Exception as e:
        logger.error(f"Ошибка при добавлении теста: {e}")
        await message.answer("❌ <b>Ошибка при добавлении теста</b>")


@dp.message(Command("activate_test"))
@rate_limit()
@require_auth()
@require_permission(Permission.COURSE_TEST_WRITE)
@require_role("teacher")
@safe_send_message
async def cmd_activate_test(message: Message, user: Dict):
    """Активация/деактивация теста"""
    api_token = user.get("api_token", "")

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ <b>Использование:</b> /activate_test ID_курса ID_теста true/false")
        return

    try:
        course_id = int(parts[1])
        test_id = int(parts[2])
        activate = parts[3].lower() == "true"

        result = await api_client.update_test_status(api_token, course_id, test_id, activate)

        if result.get("success"):
            action = "активирован" if activate else "деактивирован"
            await message.answer(f"✅ <b>Тест {action}</b>")
        else:
            await message.answer(f"❌ <b>Ошибка:</b> {result.get('error', 'Неизвестная ошибка')}")
    except ValueError:
        await message.answer("❌ <b>ID курса и ID теста должны быть числами</b>")
    except Exception as e:
        logger.error(f"Ошибка при изменении статуса теста: {e}")
        await message.answer("❌ <b>Ошибка при изменении статуса теста</b>")


@dp.message(Command("test_results"))
@rate_limit()
@require_auth()
@require_permission(Permission.TEST_ANSWER_READ)
@require_role("teacher")
@safe_send_message
async def cmd_test_results(message: Message, user: Dict):
    """Просмотр результатов теста"""
    api_token = user.get("api_token", "")

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ <b>Использование:</b> /test_results ID_теста")
        return

    try:
        test_id = int(parts[1])

        # Получаем попытки теста
        attempts = await api_client.get_test_attempts(api_token, test_id)

        if not attempts:
            await message.answer(f"📊 <b>У теста ID {test_id} нет результатов</b>")
            return

        test = data_storage.tests.get(test_id)
        test_name = test["name"] if test else f"Тест {test_id}"

        text = f"📊 <b>Результаты теста: {test_name}</b>\n\n"
        for attempt in attempts:
            text += f"👤 <b>{attempt['full_name']}</b> (ID: {attempt['user_id']})\n"
            text += f"   Оценка: {attempt['score']}%\n"
            text += f"   ID попытки: {attempt['attempt_id']}\n\n"

        await message.answer(text)
    except ValueError:
        await message.answer("❌ <b>ID теста должен быть числом</b>")
    except Exception as e:
        logger.error(f"Ошибка при получении результатов теста: {e}")
        await message.answer("❌ <b>Ошибка при загрузке результатов теста</b>")


# =========================
# КОМАНДЫ ДЛЯ ПРЕПОДАВАТЕЛЯ - ВОПРОСЫ
# =========================
@dp.message(Command("questions_list"))
@rate_limit()
@require_auth()
@require_permission(Permission.QUESTION_READ)
@require_role("teacher")
@safe_send_message
async def cmd_questions_list(message: Message, user: Dict):
    """Просмотр списка вопросов"""
    api_token = user.get("api_token", "")

    try:
        questions = await api_client.get_questions(api_token)

        if not questions:
            await message.answer("❓ <b>Вопросы не найдены</b>")
            return

        text = "❓ <b>Список вопросов</b>\n\n"
        for question in questions:
            author = data_storage.users.get(question["author_id"], {})
            author_name = author.get("full_name", f"Автор {question['author_id']}")

            text += f"🔹 <b>{question['title']}</b> (ID: {question['id']})\n"
            text += f"   Автор: {author_name}\n"
            text += f"   Версия: {question['version']}\n"
            text += f"   Вариантов ответа: {len(question['options'])}\n\n"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении вопросов: {e}")
        await message.answer("❌ <b>Ошибка при загрузке вопросов</b>")


@dp.message(Command("create_question"))
@rate_limit()
@require_auth()
@require_permission(Permission.QUESTION_ADD)
@require_role("teacher")
@safe_send_message
async def cmd_create_question(message: Message, user: Dict):
    """Создание нового вопроса"""
    api_token = user.get("api_token", "")
    user_id = user.get("user_id")

    # Формат: /create_question Название; Текст; Варианты (через |); Правильный_ответ (0-...)
    parts = message.text.split(';', 3)
    if len(parts) < 4:
        await message.answer(
            "❌ <b>Использование:</b> /create_question Название; Текст; Варианты (через |); Правильный_ответ")
        return

    title = parts[0].strip().replace('/create_question ', '')
    text = parts[1].strip()
    options = [opt.strip() for opt in parts[2].split('|')]

    try:
        correct = int(parts[3].strip())
        if correct < 0 or correct >= len(options):
            await message.answer("❌ <b>Правильный ответ должен быть в пределах количества вариантов</b>")
            return
    except ValueError:
        await message.answer("❌ <b>Правильный ответ должен быть числом</b>")
        return

    try:
        result = await api_client.create_question(api_token, title, text, options, correct, user_id)

        if result.get("success"):
            await message.answer(f"✅ <b>Вопрос создан</b>\n\nID вопроса: {result['question_id']}\nНазвание: {title}")
        else:
            await message.answer(f"❌ <b>Ошибка:</b> {result.get('error', 'Неизвестная ошибка')}")
    except Exception as e:
        logger.error(f"Ошибка при создании вопроса: {e}")
        await message.answer("❌ <b>Ошибка при создании вопроса</b>")


# =========================
# ОБНОВЛЕННАЯ КОМАНДА HELP
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
🆘 <b>Справка по командам (Преподаватель)</b>

<b>Основные команды:</b>
/start — начало работы
/help — эта справка
/status — статус системы
/profile — ваш профиль
/logout — выход из системы

<b>Управление пользователями:</b>
/users — список пользователей
/user_info [ID] — информация о пользователе
/update_fullname ID ФИО — изменить ФИО
/user_roles ID — просмотр ролей пользователя
/block_user ID true/false — блокировка/разблокировка

<b>Управление курсами:</b>
/all_courses — все курсы
/create_course Название; Описание — создать курс
/course_info ID — информация о курсе
/course_students ID — студенты курса
/enroll_student ID_курса ID_студента — записать студента

<b>Управление тестами:</b>
/course_tests ID_курса — тесты курса
/add_test ID_курса; Название — добавить тест
/activate_test ID_курса ID_теста true/false — активация теста
/test_results ID_теста — результаты теста

<b>Управление вопросами:</b>
/questions_list — все вопросы
/create_question Название; Текст; Варианты|через|вертикальную; 0 — создать вопрос

<b>Для студентов (также доступны):</b>
/tests — список тестов
/start_test ID_теста [ID_вопроса] — начать тест
/my_courses — мои курсы
/my_grades — мои оценки
/my_attempts — мои попытки
"""
        else:
            help_text = """
🆘 <b>Справка по командам (Студент)</b>

<b>Основные команды:</b>
/start — начало работы
/help — эта справка
/status — статус системы
/profile — ваш профиль
/logout — выход из системы

<b>Тесты:</b>
/tests — список тестов
/start_test ID_теста [ID_вопроса] — начать тест

<b>Мои данные:</b>
/my_courses — мои курсы
/my_grades — мои оценки
/my_attempts — мои попытки

<b>Авторизация:</b>
/login — вход в систему
/logout — выход
/logout_all — выход со всех устройств
"""
    else:
        help_text = """
🆘 <b>Справка по командам</b>

<b>Основные команды:</b>
/start — начало работы
/help — эта справка
/status — статус системы

<b>Авторизация:</b>
/login — вход в систему

<b>Технические команды:</b>
/services — информация о сервисах
/debug — отладочная информация
/ping — проверка работы бота
/echo — эхо-команда
"""

    await message.answer(help_text)


# =========================
# СУЩЕСТВУЮЩИЕ КОМАНДЫ (ОСТАВЛЯЕМ БЕЗ ИЗМЕНЕНИЙ)
# =========================
@dp.message(Command("tests"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_tests(message: Message, user: Dict):
    """Список доступных тестов с API и кнопками запуска"""
    chat_id = message.chat.id
    api_token = user.get("api_token", "")

    if not api_token:
        await message.answer("❌ <b>Ошибка авторизации</b>\n\nТокен API не найден.")
        return

    loading_msg = await message.answer("🔄 <b>Загрузка тестов...</b>")

    try:
        tests = await api_client.get_tests(api_token, DEFAULT_COURSE_ID)
        await loading_msg.delete()

        if not tests:
            text = "📚 <b>Нет доступных тестов</b>\n\nНа данный момент нет активных тестов для прохождения."
            await message.answer(text)
            return

        text = "📚 <b>Доступные тесты</b>\n\n"
        buttons = []

        for test in tests:
            test_id = test.get("id", "?")
            test_name = test.get("name") or test.get("title", f"Тест {test_id}")
            is_active = test.get("is_active", False)
            question_ids = test.get("questions", test.get("question_ids", []))

            status = "🟢" if is_active else "🔴"
            status_text = "Активен" if is_active else "Неактивен"

            text += f"{status} <b>{test_name}</b> (ID: {test_id})\n"
            text += f"   📊 Статус: {status_text}\n"
            text += f"   ❓ Вопросов: {len(question_ids)}\n"

            if question_ids:
                text += f"   📋 ID вопросов: {', '.join(map(str, question_ids[:5]))}"
                if len(question_ids) > 5:
                    text += f" ... (ещё {len(question_ids) - 5})"
                text += "\n"

            text += "\n"

            if is_active and len(question_ids) > 0:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"▶️ Начать тест: {test_name}",
                        callback_data=f"start_test_{test_id}"
                    )
                ])

        text += "\n<b>Используйте команду:</b>\n<code>/start_test ID_теста [ID_вопроса]</code>\n\n"
        text += "<b>Примеры:</b>\n"
        text += "<code>/start_test 56</code> - начать тест 56 с первого вопроса\n"
        text += "<code>/start_test 56 2</code> - начать тест 56 с вопроса 2"

        kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)

    except Exception as e:
        try:
            await loading_msg.delete()
        except:
            pass

        logger.error(f"Ошибка при получении тестов: {e}")
        await message.answer(
            f"❌ <b>Ошибка при загрузке тестов:</b>\n\n{str(e)}\n\nПопробуйте использовать /login для авторизации.")


# =========================
# ОБРАБОТЧИКИ АВТОРИЗАЦИИ ЧЕРЕЗ КОД С ВЫБОРОМ РОЛИ
# =========================
@dp.callback_query(F.data == "login_code_student")
async def callback_login_code_student(callback: CallbackQuery):
    """Авторизация через код для студента"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "code")

    # Генерируем код через заглушку
    code = await auth_service.generate_login_url(login_token, "code")

    text = f"""
👨‍🎓 <b>Авторизация студента через код</b>

Для завершения авторизации введите код в веб-клиенте:

<b>Код: <code>{code}</code></b>

⏳ <b>Код действителен 1 минуту</b>

После ввода кода нажмите "Проверить статус".

Для тестирования можете использовать команду:
<code>/simulate_auth</code>
"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.callback_query(F.data == "login_code_teacher")
async def callback_login_code_teacher(callback: CallbackQuery):
    """Авторизация через код для преподавателя"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "code")

    # Генерируем код через заглушку
    code = await auth_service.generate_login_url(login_token, "code")

    text = f"""
👨‍🏫 <b>Авторизация преподавателя через код</b>

Для завершения авторизации введите код в веб-клиенте:

<b>Код: <code>{code}</code></b>

⏳ <b>Код действителен 1 минуту</b>

После ввода кода нажмите "Проверить статус".

Для тестирования можете использовать команду:
<code>/simulate_auth</code>
"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


# =========================
# АВТОРИЗАЦИОННАЯ ЗАГЛУШКА (ОБНОВЛЕННАЯ)
# =========================
class AuthServiceStub:
    def __init__(self):
        self.login_tokens = {}  # {login_token: {status, provider, code, expires_at, created_at, user_agent, confirmed, user_data}}
        self.codes = {}  # {code: {login_token, expires_at, created_at}}
        self.code_to_token = {}  # {code: login_token} - для быстрого поиска

    async def generate_login_url(self, login_token: str, provider: str = "code") -> str:
        """Генерация URL для авторизации (заглушка для кода)"""
        # Шаг 2: Генерация случайного кода (5-6 цифр)
        code = str(secrets.randbelow(900000) + 100000)  # 6 цифр

        if provider == "code":
            # Шаг 2: Сохраняем код с временем устаревания (1 минута)
            expires_at = datetime.utcnow() + timedelta(minutes=1)
            self.codes[code] = {
                "login_token": login_token,
                "expires_at": expires_at.isoformat(),
                "created_at": datetime.utcnow().isoformat()
            }
            self.code_to_token[code] = login_token

        # Шаг 3: Сохраняем login_token с временем устаревания (5 минут)
        expires_at = datetime.utcnow() + timedelta(minutes=5)
        self.login_tokens[login_token] = {
            "status": "pending",
            "provider": provider,
            "code": code if provider == "code" else None,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "user_agent": "telegram-bot",
            "confirmed": False,
            "user_data": None,
            "role": "student"  # По умолчанию студент
        }

        # Шаг 4: Возвращаем код
        return code

    async def check_login_token(self, login_token: str) -> Optional[Dict]:
        """Проверка статуса токена авторизации"""
        if login_token not in self.login_tokens:
            return None

        token_data = self.login_tokens[login_token]

        # Проверяем не устарел ли токен (5 минут)
        expires_at = datetime.fromisoformat(token_data["expires_at"])
        if datetime.utcnow() > expires_at:
            # Удаляем устаревший токен
            if login_token in self.login_tokens:
                del self.login_tokens[login_token]
            # Удаляем связанный код если есть
            code_to_delete = None
            for code, data in self.codes.items():
                if data["login_token"] == login_token:
                    code_to_delete = code
                    break
            if code_to_delete:
                del self.codes[code_to_delete]
                del self.code_to_token[code_to_delete]
            return None

        if token_data.get("confirmed"):
            user_data = token_data.get("user_data")
            if not user_data:
                # Генерируем тестовые данные пользователя
                user_id = secrets.randbelow(1000) + 100
                email = f"user_{login_token[:8]}@example.com"
                role = token_data.get("role", "student")
                user_data = {
                    "id": user_id,
                    "email": email,
                    "role": role
                }
                token_data["user_data"] = user_data

            return {
                "status": "granted",
                "access_token": f"access_{secrets.token_hex(16)}",
                "refresh_token": f"refresh_{secrets.token_hex(16)}",
                "user": user_data
            }

        return {"status": "pending"}

    async def confirm_code(self, code: str, refresh_token: str = None, role: str = "student") -> Dict:
        """Подтверждение авторизации по коду (имитация ввода кода пользователем)"""
        # Шаг 7: Ищем код в словаре
        if code not in self.codes:
            return {"error": "Код не найден или устарел"}

        code_data = self.codes[code]
        login_token = code_data["login_token"]

        # Шаг 8: Проверяем не устарел ли код (1 минута)
        expires_at = datetime.fromisoformat(code_data["expires_at"])
        if datetime.utcnow() > expires_at:
            # Удаляем устаревший код и токен
            del self.codes[code]
            del self.code_to_token[code]
            if login_token in self.login_tokens:
                del self.login_tokens[login_token]
            return {"error": "Код устарел"}

        # Шаг 9: Проверяем токен обновления (заглушка - всегда OK)
        if refresh_token:
            # В реальности здесь была бы проверка подписи токена
            pass

        # Шаг 10: Если всё OK - подтверждаем авторизацию
        if login_token in self.login_tokens:
            # Генерируем тестовые данные пользователя из "токена обновления"
            # В реальности email брался бы из токена обновления
            user_id = secrets.randbelow(1000) + 100
            email = f"user_{secrets.token_hex(8)}@example.com"

            self.login_tokens[login_token]["confirmed"] = True
            self.login_tokens[login_token]["status"] = "granted"
            self.login_tokens[login_token]["user_data"] = {
                "id": user_id,
                "email": email,
                "role": role
            }

            # Удаляем использованный код
            del self.codes[code]
            del self.code_to_token[code]

            # Шаг 11: Возвращаем успех
            return {
                "status": "success",
                "login_token": login_token,
                "user": {
                    "id": user_id,
                    "email": email,
                    "role": role
                }
            }

        return {"error": "Токен входа не найден"}

    async def simulate_web_client_auth(self, login_token: str, role: str = "student"):
        """Имитация авторизации через веб-клиент (для тестирования)"""
        if login_token not in self.login_tokens:
            return False

        token_data = self.login_tokens[login_token]
        if token_data["provider"] != "code":
            return False

        code = token_data["code"]
        if not code:
            return False

        # Сохраняем роль
        token_data["role"] = role

        # Имитируем ввод кода в веб-клиенте
        result = await self.confirm_code(code, "dummy_refresh_token", role)
        return "error" not in result

    def set_token_role(self, login_token: str, role: str):
        """Установка роли для токена авторизации"""
        if login_token in self.login_tokens:
            self.login_tokens[login_token]["role"] = role
            return True
        return False


auth_service = AuthServiceStub()


# =========================
# ОБРАБОТЧИК ПРОВЕРКИ СТАТУСА АВТОРИЗАЦИИ
# =========================
@dp.callback_query(F.data.startswith("check_auth_"))
async def callback_check_auth(callback: CallbackQuery):
    """Проверка статуса авторизации"""
    login_token = callback.data[11:]
    result = await auth_service.check_login_token(login_token)

    if not result:
        await callback.answer("❌ Токен не найден или истек")
    elif result.get("status") == "pending":
        await callback.answer("⏳ Ожидание подтверждения авторизации")

        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
            ])
            await callback.message.edit_reply_markup(reply_markup=kb)
        except:
            pass
    elif result.get("status") == "granted":
        user_data = result.get("user", {})
        user_id = user_data.get("id", secrets.randbelow(1000) + 100)
        email = user_data.get("email", f"user_{login_token[:8]}@example.com")
        role = user_data.get("role", "student")

        await set_user_authorized(callback.from_user.id, user_id, email, role)

        await callback.answer("✅ Авторизация успешна!")
        await callback.message.edit_text(
            f"✅ <b>Авторизация завершена!</b>\n\nДобро пожаловать, {email}\n\nРоль: {role}",
            reply_markup=None
        )


# =========================
# КОМАНДА ДЛЯ ИМИТАЦИИ ВЕБ-АВТОРИЗАЦИИ
# =========================
@dp.message(Command("simulate_auth"))
@rate_limit()
@safe_send_message
async def cmd_simulate_auth(message: Message):
    """Имитация авторизации через веб-клиент"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user or user.get("status") != UserStatus.ANONYMOUS:
        await message.answer("❌ <b>Нет ожидающей авторизации</b>\n\nСначала используйте /login и выберите Code.")
        return

    login_token = user.get("login_token")
    if not login_token:
        await message.answer("❌ <b>Ошибка: токен входа не найден</b>")
        return

    # Определяем роль из данных пользователя или по умолчанию студент
    role = user.get("role_choice", "student")

    # Имитируем авторизацию через веб-клиент
    result = await auth_service.simulate_web_client_auth(login_token, role)

    if result:
        await message.answer(
            "✅ <b>Имитация веб-авторизации успешна!</b>\n\nТеперь нажмите 'Проверить статус' или подождите несколько секунд.")
    else:
        await message.answer("❌ <b>Ошибка имитации авторизации</b>\n\nВозможно, код устарел или токен не найден.")


# =========================
# КОМАНДА ДЛЯ ПРОСМОТРА ПРОФИЛЯ
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

    # Получаем информацию о пользователе из API
    api_token = current_user.get("api_token", "")
    user_id = current_user.get("user_id")

    try:
        user_info = await api_client.get_user_info(api_token, user_id)

        if not user_info:
            user_info = {
                "full_name": "Неизвестно",
                "email": current_user.get("email", "Неизвестно"),
                "role": current_user.get("role", "student"),
                "is_blocked": False
            }
    except:
        user_info = {
            "full_name": "Неизвестно",
            "email": current_user.get("email", "Неизвестно"),
            "role": current_user.get("role", "student"),
            "is_blocked": False
        }

    # Форматируем дату авторизации (по Москве)
    auth_date = "Неизвестно"
    if current_user.get("authorized_at"):
        try:
            auth_dt_utc = datetime.fromisoformat(current_user["authorized_at"].replace('Z', '+00:00'))
            auth_dt_msk = auth_dt_utc + timedelta(hours=3)
            auth_date = auth_dt_msk.strftime("%d.%m.%Y %H:%M (MSK)")
        except:
            auth_date = current_user["authorized_at"]

    role = user_info.get("role", "student")
    role_text = "👨‍🏫 Преподаватель" if role == "teacher" else "👨‍🎓 Студент"
    permissions = current_user.get("permissions", [])

    # Получаем курсы пользователя
    try:
        user_data = await api_client.get_user_courses_grades(api_token, user_id)
        courses_count = len(user_data.get("courses", []))
        attempts = user_data.get("attempts", [])
        completed_attempts = [a for a in attempts if a.get("status") == "completed"]
        average_score = sum(a.get("score", 0) for a in completed_attempts) / len(
            completed_attempts) if completed_attempts else 0
    except:
        courses_count = 0
        average_score = 0

    text = f"""
👤 <b>Профиль пользователя</b>

<b>Основная информация:</b>
📧 <b>Email:</b> {user_info.get('email', 'Неизвестно')}
👤 <b>ФИО:</b> {user_info.get('full_name', 'Неизвестно')}
🔑 <b>Роль:</b> {role_text}
🔢 <b>ID пользователя:</b> {user_id}

<b>Статистика:</b>
📚 <b>Курсов:</b> {courses_count}
📊 <b>Пройдено тестов:</b> {len(completed_attempts)}
🎯 <b>Средний балл:</b> {average_score:.1f}%

<b>Разрешения:</b>
{', '.join(permissions[:5]) if permissions else 'Базовые разрешения'}
{f'... и ещё {len(permissions) - 5}' if len(permissions) > 5 else ''}

<b>Сессия в Telegram:</b>
🤖 <b>Авторизован:</b> {auth_date}
🔐 <b>Статус:</b> {'🔴 Заблокирован' if user_info.get('is_blocked') else '🟢 Активен'}
"""

    await message.answer(text)


# =========================
# КОМАНДА ДЛЯ ПРОСМОТРА СТАТУСА
# =========================
@dp.message(Command("status"))
@rate_limit()
@safe_send_message
async def cmd_status(message: Message):
    chat_id = message.chat.id
    user = await get_user(chat_id)

    current_time = format_moscow_time()

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
⏰ <b>Текущее время (MSK):</b> {current_time}
👥 <b>Активных пользователей:</b> {active_users_count}
📊 <b>Выполнено команд:</b> {commands_count}

<b>Сервисы:</b>
• Redis — {redis_status}
• Telegram Bot — 🟢 онлайн
• API Backend — 🟢 {API_BASE_URL}
"""
    await message.answer(text)


# =========================
# КОМАНДА ДЛЯ ВЫХОДА
# =========================
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

    await message.answer("🚪 <b>Вы вышли из системы</b>")

    stats.remove_active_user(chat_id)
    await delete_user(chat_id)


# =========================
# КОМАНДА ДЛЯ ВЫХОДА СО ВСЕХ УСТРОЙСТВ
# =========================
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


# =========================
# КОМАНДА ДЛЯ ПРОСМОТРА СЕРВИСОВ
# =========================
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

<b>Веб-сервер</b>
• Nginx — прокси и статика
• HTTP сервер — health-check

<b>Авторизация</b>
• Режим Code — 6-значный код (1 минута)
• Токен входа — 5 минут
• Поддержка GitHub/Yandex (заглушки)
"""
    await message.answer(text)


# =========================
# КОМАНДА ДЛЯ ОТЛАДКИ
# =========================
@dp.message(Command("debug"))
@rate_limit()
@safe_send_message
async def cmd_debug(message: Message):
    chat_id = message.chat.id
    user = await get_user(chat_id)

    authorized_users = await get_all_authorized_users()

    # Статистика авторизации
    auth_stats = {
        "pending_tokens": len(auth_service.login_tokens),
        "active_codes": len(auth_service.codes),
        "code_to_token": len(auth_service.code_to_token)
    }

    text = f"""
🐛 <b>Отладочная информация</b>

<b>Система:</b>
• Chat ID: <code>{chat_id}</code>
• Redis: {"🟢 подключен" if redis_client.connected else "🔴 оффлайн"}
• API: {API_BASE_URL}
• Время (MSK): {format_moscow_time()}
• HTTP порт: {HTTP_PORT}

<b>Пользователь:</b>
• Статус: {user.get('status') if user else 'UNKNOWN'}
• User ID: {user.get('user_id') if user else 'Нет'}
• Email: {user.get('email') if user else 'Нет'}
• Роль: {user.get('role') if user else 'Нет'}

<b>Статистика авторизации:</b>
• Ожидающих токенов: {auth_stats['pending_tokens']}
• Активных кодов: {auth_stats['active_codes']}
• Сопоставлений код-токен: {auth_stats['code_to_token']}

<b>Статистика бота:</b>
• Активных пользователей: {len(authorized_users)}
• Выполнено команд: {stats.commands_count}
"""
    await message.answer(text)


# =========================
# КОМАНДА ДЛЯ ПРОВЕРКИ РАБОТОСПОСОБНОСТИ
# =========================
@dp.message(Command("ping"))
@rate_limit()
@safe_send_message
async def cmd_ping(message: Message):
    await message.answer("🏓 <b>Pong!</b>\n\n🤖 Бот работает корректно.\n⚡ Все системы в норме.")


# =========================
# КОМАНДА ECHO
# =========================
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
# ОБРАБОТЧИК КНОПКИ ОТМЕНЫ АВТОРИЗАЦИИ
# =========================
@dp.callback_query(F.data == "cancel_auth")
async def callback_cancel_auth(callback: CallbackQuery):
    chat_id = callback.from_user.id
    await delete_user(chat_id)
    await callback.answer("❌ Авторизация отменена")
    await callback.message.edit_text("🚪 <b>Авторизация отменена</b>", reply_markup=None)


# =========================
# ОБРАБОТЧИК КНОПКИ АВТОРИЗАЦИИ
# =========================
@dp.callback_query(F.data == "login")
async def callback_login(callback: CallbackQuery):
    await callback.answer()
    await cmd_login(callback.message)


# =========================
# ОБРАБОТЧИК ЗАПУСКА ТЕСТА ЧЕРЕЗ КНОПКУ
# =========================
@dp.callback_query(F.data.startswith("start_test_"))
async def callback_start_test(callback: CallbackQuery):
    """Запуск теста через кнопку"""
    try:
        test_id = int(callback.data[11:])
        chat_id = callback.from_user.id
        user = await get_user(chat_id)

        if not user:
            await callback.answer("❌ Требуется авторизация")
            return

        api_token = user.get("api_token", "")

        if not api_token:
            await callback.answer("❌ Ошибка авторизации")
            return

        # Начинаем тест
        loading_msg = await callback.message.answer(f"🔄 <b>Запуск теста #{test_id}...</b>")

        try:
            # Создаем попытку
            result = await api_client.create_attempt(api_token, test_id, user["user_id"])

            if "error" in result:
                await loading_msg.delete()
                await callback.answer(f"❌ {result['error']}")
                return

            attempt_id = result.get("attempt_id")
            if not attempt_id:
                await loading_msg.delete()
                await callback.answer("❌ Не удалось начать тест")
                return

            # Получаем вопросы теста
            test = data_storage.tests.get(test_id)
            if not test:
                await loading_msg.delete()
                await callback.answer("❌ Тест не найден")
                return

            question_ids = test.get("questions", [])

            if not question_ids:
                await loading_msg.delete()
                await callback.answer("❌ В тесте нет вопросов")
                return

            # Сохраняем контекст теста
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
                f"test_context:{chat_id}",
                3600,
                json.dumps(test_context)
            )

            # Получаем первый вопрос
            first_question_id = question_ids[0]
            question_data = await api_client.get_question_details(api_token, first_question_id)

            text = f"""
🧪 <b>Начинаем тест #{test_id}</b>

<b>Название:</b> {test.get('name', f'Тест {test_id}')}
<b>ID попытки:</b> {attempt_id}
<b>Всего вопросов:</b> {len(question_ids)}
<b>Текущий вопрос:</b> 1 из {len(question_ids)}

<b>Вопрос:</b>
{question_data.get('text', 'Текст вопроса')}
"""

            # Создаем кнопки для вариантов ответов
            buttons = []
            options = question_data.get("options", ["Вариант 1", "Вариант 2", "Вариант 3"])

            for i, option in enumerate(options):
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{i + 1}. {option}",
                        callback_data=f"answer_{attempt_id}_{first_question_id}_{i}"
                    )
                ])

            # Добавляем кнопку отмены
            buttons.append([
                InlineKeyboardButton(text="❌ Отменить тест", callback_data="cancel_test")
            ])

            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            await loading_msg.delete()
            await callback.message.answer(text, reply_markup=kb)
            await callback.answer()

        except Exception as e:
            await loading_msg.delete()
            logger.error(f"Error starting test: {e}")
            await callback.answer(f"❌ Ошибка: {str(e)}")

    except Exception as e:
        logger.error(f"Error in callback_start_test: {e}")
        await callback.answer("❌ Ошибка запуска теста")


# =========================
# ОБРАБОТКА ОТВЕТОВ ЧЕРЕЗ КНОПКИ
# =========================
@dp.callback_query(F.data.startswith("answer_"))
async def handle_answer_callback(callback: CallbackQuery):
    """Обработка ответов через кнопки"""
    try:
        # Разбираем callback_data: answer_attemptId_questionId_optionIndex
        parts = callback.data.split("_")
        if len(parts) < 4:
            await callback.answer("❌ Ошибка формата")
            return

        attempt_id = int(parts[1])
        question_id = int(parts[2])
        option_index = int(parts[3])

        chat_id = callback.from_user.id
        user = await get_user(chat_id)

        if not user:
            await callback.answer("❌ Требуется авторизация")
            return

        api_token = user.get("api_token", "")

        # Получаем контекст теста
        context_data = await redis_client.get(f"test_context:{chat_id}")
        if not context_data:
            await callback.answer("❌ Нет активного теста")
            return

        context = json.loads(context_data)

        # Проверяем, что attempt_id совпадает
        if context.get("attempt_id") != attempt_id:
            await callback.answer("❌ Неверная попытка теста")
            return

        # Отправляем ответ через API
        try:
            result = await api_client.update_attempt_answer(api_token, attempt_id, question_id, option_index)
            if "error" in result:
                await callback.answer(f"❌ {result['error']}")
                return
            await callback.answer(f"✅ Ответ {option_index + 1} сохранен")
        except Exception as e:
            logger.error(f"Ошибка отправки ответа: {e}")
            await callback.answer("❌ Ошибка отправки ответа")
            return

        # Обновляем контекст
        current_index = context.get("current_question_index", 0)
        context["answers"][question_id] = option_index
        context["current_question_index"] = current_index + 1

        # Проверяем, закончен ли тест
        question_ids = context.get("question_ids", [])
        if current_index + 1 >= len(question_ids):
            # Тест завершен
            await redis_client.delete(f"test_context:{chat_id}")

            # Завершаем попытку через API
            try:
                result = await api_client.complete_attempt(api_token, attempt_id)

                if "error" in result:
                    logger.error(f"Ошибка завершения попытки: {result['error']}")
                    await callback.message.answer(
                        f"🎉 <b>Тест завершен!</b>\n\nОшибка при завершении: {result['error']}")
                    return

                score = result.get("score", 0)

                # Подсчитываем правильные ответы
                correct_count = 0
                for qid, answer in context["answers"].items():
                    question_data = await api_client.get_question_details(api_token, qid)
                    if question_data.get("correct") == answer:
                        correct_count += 1

                percentage = int((correct_count / len(question_ids)) * 100) if question_ids else 0

                text = f"""
🎉 <b>Тест завершен!</b>

<b>Ваш результат:</b> {score}%
<b>Правильных ответов:</b> {correct_count} из {len(question_ids)} ({percentage}%)

🏆 <b>Отличная работа!</b>

Ваши ответы сохранены в системе.
"""
                await callback.message.answer(text)
            except Exception as e:
                logger.error(f"Ошибка завершения теста: {e}")
                await callback.message.answer(f"🎉 <b>Тест завершен!</b>\n\nОшибка при получении результата: {str(e)}")
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
<b>ID вопроса:</b> {next_question_id}

{question_data.get('text', 'Текст вопроса')}
"""
            # Создаем кнопки для вариантов ответов
            buttons = []
            options = question_data.get("options", ["Вариант 1", "Вариант 2", "Вариант 3"])

            for i, option in enumerate(options):
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{i + 1}. {option}",
                        callback_data=f"answer_{attempt_id}_{next_question_id}_{i}"
                    )
                ])

            # Добавляем кнопку отмены
            buttons.append([
                InlineKeyboardButton(text="❌ Отменить тест", callback_data="cancel_test")
            ])

            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.message.answer(text, reply_markup=kb)

    except Exception as e:
        logger.error(f"Error processing answer callback: {e}")
        await callback.answer("❌ Ошибка обработки ответа")


# =========================
# ОБРАБОТЧИК ОТМЕНЫ ТЕСТА
# =========================
@dp.callback_query(F.data == "cancel_test")
async def callback_cancel_test(callback: CallbackQuery):
    """Отмена теста"""
    chat_id = callback.from_user.id
    await redis_client.delete(f"test_context:{chat_id}")
    await callback.answer("❌ Тест отменен")
    await callback.message.answer("🚫 <b>Тест отменен</b>\n\nВы можете начать новый тест с помощью /start_test.")


# =========================
# КОМАНДА ЗАПУСКА ТЕСТА ЧЕРЕЗ КОМАНДУ
# =========================
@dp.message(Command("start_test"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_start_test(message: Message, user: Dict):
    """Запуск теста по ID теста и ID вопроса"""
    chat_id = message.chat.id
    api_token = user.get("api_token", "")

    command_text = message.text or ""
    parts = command_text.split()

    if len(parts) < 2:
        await message.answer(
            "❌ <b>Использование:</b> <code>/start_test ID_теста [ID_вопроса]</code>\n\nПримеры:\n<code>/start_test 56</code> - начать тест 56\n<code>/start_test 56 2</code> - начать тест 56 с вопроса 2")
        return

    try:
        test_id = int(parts[1])
        question_id = int(parts[2]) if len(parts) > 2 else None
    except ValueError:
        await message.answer("❌ <b>Ошибка:</b> ID теста и ID вопроса должны быть числами")
        return

    if not api_token:
        await message.answer("❌ <b>Ошибка авторизации</b>\n\nТокен API не найден.")
        return

    loading_msg = await message.answer(f"🔄 <b>Запуск теста #{test_id}...</b>")

    try:
        # Создаем попытку
        result = await api_client.create_attempt(api_token, test_id, user["user_id"])

        if "error" in result:
            await loading_msg.delete()
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
            return

        attempt_id = result.get("attempt_id")
        if not attempt_id:
            await loading_msg.delete()
            await message.answer("❌ <b>Ошибка:</b> Не удалось начать тест. Попробуйте позже.")
            return

        # Получаем вопросы теста
        test = data_storage.tests.get(test_id)
        if not test:
            await loading_msg.delete()
            await message.answer("❌ <b>Ошибка:</b> Тест не найден.")
            return

        question_ids = test.get("questions", [])

        if not question_ids:
            await loading_msg.delete()
            await message.answer("❌ <b>Ошибка:</b> В тесте нет вопросов.")
            return

        # Определяем, с какого вопроса начинать
        start_question_index = 0
        if question_id:
            try:
                start_question_index = question_ids.index(question_id)
            except ValueError:
                # Если вопрос не найден в списке, начинаем с ближайшего доступного
                found = False
                for i, qid in enumerate(question_ids):
                    if qid >= question_id:
                        start_question_index = i
                        found = True
                        break

                if not found:
                    await loading_msg.delete()
                    await message.answer(f"❌ <b>Ошибка:</b> Вопрос с ID {question_id} не найден в тесте.")
                    return

        # Сохраняем контекст теста
        test_context = {
            "test_id": test_id,
            "attempt_id": attempt_id,
            "question_ids": question_ids,
            "current_question_index": start_question_index,
            "answers": {},
            "started_at": datetime.now().isoformat(),
            "api_token": api_token,
            "user_id": user.get("user_id")
        }

        await redis_client.setex(
            f"test_context:{chat_id}",
            3600,
            json.dumps(test_context)
        )

        # Получаем текущий вопрос
        current_question_id = question_ids[start_question_index]
        question_data = await api_client.get_question_details(api_token, current_question_id)

        text = f"""
🧪 <b>Начинаем тест #{test_id}</b>

<b>Название:</b> {test.get('name', f'Тест {test_id}')}
<b>ID попытки:</b> {attempt_id}
<b>Всего вопросов:</b> {len(question_ids)}
<b>Текущий вопрос:</b> {start_question_index + 1} из {len(question_ids)}
<b>ID вопроса:</b> {current_question_id}

<b>Вопрос:</b>
{question_data.get('text', 'Текст вопроса')}
"""

        # Создаем кнопки для вариантов ответов
        buttons = []
        options = question_data.get("options", ["Вариант 1", "Вариант 2", "Вариант 3"])

        for i, option in enumerate(options):
            buttons.append([
                InlineKeyboardButton(
                    text=f"{i + 1}. {option}",
                    callback_data=f"answer_{attempt_id}_{current_question_id}_{i}"
                )
            ])

        # Добавляем кнопку отмены
        buttons.append([
            InlineKeyboardButton(text="❌ Отменить тест", callback_data="cancel_test")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await loading_msg.delete()
        await message.answer(text, reply_markup=kb)

    except Exception as e:
        try:
            await loading_msg.delete()
        except:
            pass

        logger.error(f"Error starting test: {e}")
        await message.answer(f"❌ <b>Ошибка при начале теста:</b>\n\n{str(e)}")


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