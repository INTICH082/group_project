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
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "https://3280a8be-440f-4174-bbac-ed4003e901ff.tunnel4.com")
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
# REAL AUTH SERVICE - ДЛЯ ПОДКЛЮЧЕНИЯ К МОДУЛЮ АВТОРИЗАЦИИ
# =========================
class RealAuthService:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.session = None
        self.timeout = 30  # Таймаут для запросов
        self.use_real_service = True  # Флаг использования реального сервиса

    async def ensure_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        if self.session:
            await self.session.close()

    async def generate_login_url(self, login_token: str, provider: str = "code", role: str = "student") -> str:
        """Генерация URL для авторизации через реальный сервис"""
        await self.ensure_session()

        endpoint = "/api/auth/login/start"
        url = f"{self.base_url}{endpoint}"

        payload = {
            "login_token": login_token,
            "provider": provider,
            "role": role,
            "user_agent": "telegram-bot"
        }

        headers = {
            "Content-Type": "application/json"
        }

        try:
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if provider == "code" and "code" in data:
                        return data["code"]
                    elif provider in ["github", "yandex"] and "url" in data:
                        return data["url"]
                    else:
                        logger.error(f"Некорректный ответ от сервиса авторизации: {data}")
                        raise Exception("Некорректный ответ от сервиса авторизации")
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка сервиса авторизации {response.status}: {error_text}")
                    raise Exception(f"Ошибка сервиса авторизации: {response.status}")
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка соединения с сервисом авторизации: {e}")
            raise Exception(f"Сервис авторизации недоступен: {e}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка в сервисе авторизации: {e}")
            raise Exception(f"Ошибка при обращении к сервису авторизации: {e}")

    async def check_login_token(self, login_token: str) -> Optional[Dict]:
        """Проверка статуса токена авторизации через реальный сервис"""
        await self.ensure_session()

        endpoint = f"/api/auth/login/check?login_token={login_token}"
        url = f"{self.base_url}{endpoint}"

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                elif response.status == 404:
                    # Токен не найден
                    return None
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка проверки токена {response.status}: {error_text}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка соединения при проверке токена: {e}")
            return None
        except Exception as e:
            logger.error(f"Неизвестная ошибка при проверке токена: {e}")
            return None

    async def confirm_code(self, code: str, refresh_token: str = None, role: str = "student") -> Dict:
        """Подтверждение авторизации по коду через реальный сервис"""
        await self.ensure_session()

        endpoint = "/api/auth/login/confirm"
        url = f"{self.base_url}{endpoint}"

        payload = {
            "code": code,
            "refresh_token": refresh_token or "telegram_bot_dummy_token",
            "role": role
        }

        headers = {
            "Content-Type": "application/json"
        }

        try:
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка подтверждения кода {response.status}: {error_text}")
                    return {"error": f"Ошибка подтверждения: {response.status}"}
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка соединения при подтверждении кода: {e}")
            return {"error": f"Сервис недоступен: {e}"}
        except Exception as e:
            logger.error(f"Неизвестная ошибка при подтверждении кода: {e}")
            return {"error": f"Ошибка подтверждения: {e}"}


# =========================
# HYBRID AUTH SERVICE (ОБЪЕДИНЕННЫЙ) - ИСПОЛЬЗУЕТ РЕАЛЬНЫЙ СЕРВИС ИЛИ ЗАГЛУШКУ
# =========================
class HybridAuthService:
    def __init__(self, base_url: str = None):
        self.real_service = None
        if base_url:
            self.real_service = RealAuthService(base_url)

        # Заглушка для резервного режима
        self.login_tokens = {}
        self.codes = {}
        self.code_to_token = {}

    async def generate_login_url(self, login_token: str, provider: str = "code", role: str = "student") -> str:
        """Генерация URL для авторизации с приоритетом реального сервиса"""
        if self.real_service and self.real_service.use_real_service:
            try:
                return await self.real_service.generate_login_url(login_token, provider, role)
            except Exception as e:
                logger.warning(f"Реальный сервис недоступен, используем заглушку: {e}")
                # Продолжаем с заглушкой

        # Используем заглушку
        if provider == "code":
            code = str(secrets.randbelow(900000) + 100000)
            expires_at = datetime.utcnow() + timedelta(minutes=1)
            self.codes[code] = {
                "login_token": login_token,
                "expires_at": expires_at.isoformat(),
                "created_at": datetime.utcnow().isoformat()
            }
            self.code_to_token[code] = login_token

            token_expires_at = datetime.utcnow() + timedelta(minutes=5)
            self.login_tokens[login_token] = {
                "status": "pending",
                "provider": provider,
                "code": code,
                "expires_at": token_expires_at.isoformat(),
                "created_at": datetime.utcnow().isoformat(),
                "user_agent": "telegram-bot",
                "confirmed": False,
                "user_data": None,
                "role": role
            }
            return code
        elif provider == "github":
            token_expires_at = datetime.utcnow() + timedelta(minutes=5)
            self.login_tokens[login_token] = {
                "status": "pending",
                "provider": provider,
                "code": None,
                "expires_at": token_expires_at.isoformat(),
                "created_at": datetime.utcnow().isoformat(),
                "user_agent": "telegram-bot",
                "confirmed": False,
                "user_data": None,
                "role": role
            }
            return f"https://github.com/login/oauth/authorize?client_id=test&state={login_token}&scope=user"
        elif provider == "yandex":
            token_expires_at = datetime.utcnow() + timedelta(minutes=5)
            self.login_tokens[login_token] = {
                "status": "pending",
                "provider": provider,
                "code": None,
                "expires_at": token_expires_at.isoformat(),
                "created_at": datetime.utcnow().isoformat(),
                "user_agent": "telegram-bot",
                "confirmed": False,
                "user_data": None,
                "role": role
            }
            return f"https://oauth.yandex.ru/authorize?response_type=code&client_id=test&state={login_token}"
        else:
            return ""

    async def check_login_token(self, login_token: str) -> Optional[Dict]:
        """Проверка статуса токена с приоритетом реального сервиса"""
        if self.real_service and self.real_service.use_real_service:
            try:
                result = await self.real_service.check_login_token(login_token)
                if result is not None:
                    return result
            except Exception as e:
                logger.warning(f"Реальный сервис недоступен при проверке токена, используем заглушку: {e}")

        # Используем заглушку
        if login_token not in self.login_tokens:
            return None

        token_data = self.login_tokens[login_token]
        expires_at = datetime.fromisoformat(token_data["expires_at"])
        if datetime.utcnow() > expires_at:
            if login_token in self.login_tokens:
                del self.login_tokens[login_token]
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
        """Подтверждение авторизации по коду с приоритетом реального сервиса"""
        if self.real_service and self.real_service.use_real_service:
            try:
                result = await self.real_service.confirm_code(code, refresh_token, role)
                if "error" not in result:
                    return result
            except Exception as e:
                logger.warning(f"Реальный сервис недоступен при подтверждении кода, используем заглушку: {e}")

        # Используем заглушку
        if code not in self.codes:
            return {"error": "Код не найден или устарел"}

        code_data = self.codes[code]
        login_token = code_data["login_token"]
        expires_at = datetime.fromisoformat(code_data["expires_at"])
        if datetime.utcnow() > expires_at:
            del self.codes[code]
            del self.code_to_token[code]
            if login_token in self.login_tokens:
                del self.login_tokens[login_token]
            return {"error": "Код устарел"}

        if login_token in self.login_tokens:
            user_id = secrets.randbelow(1000) + 100
            email = f"user_{secrets.token_hex(8)}@example.com"

            self.login_tokens[login_token]["confirmed"] = True
            self.login_tokens[login_token]["status"] = "granted"
            self.login_tokens[login_token]["user_data"] = {
                "id": user_id,
                "email": email,
                "role": role
            }

            del self.codes[code]
            del self.code_to_token[code]

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
        """Имитация авторизации через веб-клиент (только для заглушки)"""
        if login_token not in self.login_tokens:
            return False

        token_data = self.login_tokens[login_token]
        if token_data["provider"] != "code":
            return False

        code = token_data["code"]
        if not code:
            return False

        token_data["role"] = role
        result = await self.confirm_code(code, "dummy_refresh_token", role)
        return "error" not in result

    def set_token_role(self, login_token: str, role: str):
        """Установка роли для токена авторизации (только для заглушки)"""
        if login_token in self.login_tokens:
            self.login_tokens[login_token]["role"] = role
            return True
        return False


# Инициализируем гибридный сервис авторизации
auth_service = HybridAuthService(AUTH_SERVICE_URL)


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
# API CLIENT - УЛУЧШЕННАЯ ВЕРСИЯ
# =========================
class APIClient:
    def __init__(self, base_url: str, jwt_secret: str):
        self.base_url = base_url.rstrip('/')
        self.jwt_secret = jwt_secret
        self.session = None

    async def ensure_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)  # ← Строка с таймаутами
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
            async with self.session.request(method, url, headers=headers, json=data,
                                            timeout=30) as response:  # ← Таймаут 30 секунд
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
# ОБНОВЛЕННАЯ КОМАНДА LOGIN С ВЫБОРОМ РОЛИ (3 КНОПКИ)
# =========================
@dp.message(Command("login"))
@rate_limit()
@safe_send_message
async def cmd_login(message: Message):
    """Показ выбора роли для авторизации - ТОЛЬКО 3 КНОПКИ"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await message.answer(f"✅ <b>Вы уже авторизованы как {user.get('email')}</b>\n\nИспользуйте /logout для выхода.")
        return

    text = """
🔐 <b>Выберите вашу роль:</b>

Выберите кем вы являетесь в системе:
"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🎓 Я студент", callback_data="login_student")],
        [InlineKeyboardButton(text="👨‍🏫 Я преподаватель", callback_data="login_teacher")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await message.answer(text, reply_markup=kb)


# =========================
# ВЫБОР СЕРВИСА АВТОРИЗАЦИИ ДЛЯ СТУДЕНТА (3 СЕРВИСА)
# =========================
@dp.callback_query(F.data == "login_student")
async def callback_login_student(callback: CallbackQuery):
    """Выбор сервиса авторизации для студента - 3 СЕРВИСА"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    text = """
👨‍🎓 <b>Авторизация как студент</b>

Выберите сервис для авторизации:
"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔢 Code", callback_data="login_code_student")],
        [InlineKeyboardButton(text="🐙 GitHub", callback_data="login_github_student")],
        [InlineKeyboardButton(text="🟦 Яндекс ID", callback_data="login_yandex_student")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# =========================
# ВЫБОР СЕРВИСА АВТОРИЗАЦИИ ДЛЯ ПРЕПОДАВАТЕЛЯ (3 СЕРВИСА)
# =========================
@dp.callback_query(F.data == "login_teacher")
async def callback_login_teacher(callback: CallbackQuery):
    """Выбор сервиса авторизации для преподавателя - 3 СЕРВИСА"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    text = """
👨‍🏫 <b>Авторизация как преподаватель</b>

Выберите сервис для авторизации:
"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔢 Code", callback_data="login_code_teacher")],
        [InlineKeyboardButton(text="🐙 GitHub", callback_data="login_github_teacher")],
        [InlineKeyboardButton(text="🟦 Яндекс ID", callback_data="login_yandex_teacher")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# =========================
# АВТОРИЗАЦИЯ ЧЕРЕЗ CODE ДЛЯ СТУДЕНТА
# =========================
@dp.callback_query(F.data == "login_code_student")
async def callback_login_code_student(callback: CallbackQuery):
    """Авторизация через Code для студента"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "code")

    # Генерируем код через гибридный сервис
    code = await auth_service.generate_login_url(login_token, "code", "student")

    text = f"""
👨‍🎓 <b>Авторизация студента через Code</b>

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
# АВТОРИЗАЦИЯ ЧЕРЕЗ GITHUB ДЛЯ СТУДЕНТА
# =========================
@dp.callback_query(F.data == "login_github_student")
async def callback_login_github_student(callback: CallbackQuery):
    """Авторизация через GitHub для студента"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "github")

    # Генерируем URL через гибридный сервис
    url = await auth_service.generate_login_url(login_token, "github", "student")

    text = f"""
👨‍🎓 <b>Авторизация студента через GitHub</b>

Для завершения авторизации перейдите по ссылке:

<b>Ссылка: <code>{url}</code></b>

⏳ <b>Ссылка действительна 5 минут</b>

После подтверждения в браузере нажмите "Проверить статус".

<em>Примечание: Это {'реальная' if auth_service.real_service and auth_service.real_service.use_real_service else 'заглушка'} ссылка на GitHub OAuth.</em>
"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


# =========================
# АВТОРИЗАЦИЯ ЧЕРЕЗ YANDEX ID ДЛЯ СТУДЕНТА
# =========================
@dp.callback_query(F.data == "login_yandex_student")
async def callback_login_yandex_student(callback: CallbackQuery):
    """Авторизация через Яндекс ID для студента"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "yandex")

    # Генерируем URL через гибридный сервис
    url = await auth_service.generate_login_url(login_token, "yandex", "student")

    text = f"""
👨‍🎓 <b>Авторизация студента через Яндекс ID</b>

Для завершения авторизации перейдите по ссылке:

<b>Ссылка: <code>{url}</code></b>

⏳ <b>Ссылка действительна 5 минут</b>

После подтверждения в браузере нажмите "Проверить статус".

<em>Примечание: Это {'реальная' if auth_service.real_service and auth_service.real_service.use_real_service else 'заглушка'} ссылка на Яндекс OAuth.</em>
"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


# =========================
# АВТОРИЗАЦИЯ ЧЕРЕЗ CODE ДЛЯ ПРЕПОДАВАТЕЛЯ
# =========================
@dp.callback_query(F.data == "login_code_teacher")
async def callback_login_code_teacher(callback: CallbackQuery):
    """Авторизация через Code для преподавателя"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "code")

    # Генерируем код через гибридный сервис
    code = await auth_service.generate_login_url(login_token, "code", "teacher")

    text = f"""
👨‍🏫 <b>Авторизация преподавателя через Code</b>

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
# АВТОРИЗАЦИЯ ЧЕРЕЗ GITHUB ДЛЯ ПРЕПОДАВАТЕЛЯ
# =========================
@dp.callback_query(F.data == "login_github_teacher")
async def callback_login_github_teacher(callback: CallbackQuery):
    """Авторизация через GitHub для преподавателя"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "github")

    # Генерируем URL через гибридный сервис
    url = await auth_service.generate_login_url(login_token, "github", "teacher")

    text = f"""
👨‍🏫 <b>Авторизация преподавателя через GitHub</b>

Для завершения авторизации перейдите по ссылке:

<b>Ссылка: <code>{url}</code></b>

⏳ <b>Ссылка действительна 5 минут</b>

После подтверждения в браузере нажмите "Проверить статус".

<em>Примечание: Это {'реальная' if auth_service.real_service and auth_service.real_service.use_real_service else 'заглушка'} ссылка на GitHub OAuth.</em>
"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


# =========================
# АВТОРИЗАЦИЯ ЧЕРЕЗ YANDEX ID ДЛЯ ПРЕПОДАВАТЕЛЯ
# =========================
@dp.callback_query(F.data == "login_yandex_teacher")
async def callback_login_yandex_teacher(callback: CallbackQuery):
    """Авторизация через Яндекс ID для преподавателя"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "yandex")

    # Генерируем URL через гибридный сервис
    url = await auth_service.generate_login_url(login_token, "yandex", "teacher")

    text = f"""
👨‍🏫 <b>Авторизация преподавателя через Яндекс ID</b>

Для завершения авторизации перейдите по ссылке:

<b>Ссылка: <code>{url}</code></b>

⏳ <b>Ссылка действительна 5 минут</b>

После подтверждения в браузере нажмите "Проверить статус".

<em>Примечание: Это {'реальная' if auth_service.real_service and auth_service.real_service.use_real_service else 'заглушка'} ссылка на Яндекс OAuth.</em>
"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


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
# ОБРАБОТЧИК ОТМЕНЫ АВТОРИЗАЦИИ
# =========================
@dp.callback_query(F.data == "cancel_auth")
async def callback_cancel_auth(callback: CallbackQuery):
    """Отмена авторизации"""
    chat_id = callback.from_user.id

    # Удаляем пользователя из состояния анонимного
    await delete_user(chat_id)

    # Показываем стартовое сообщение
    await callback.message.edit_text(
        "❌ <b>Авторизация отменена</b>\n\n"
        "Для начала работы используйте команду /start",
        reply_markup=None
    )
    await callback.answer()


# =========================
# КОМАНДА ДЛЯ ИМИТАЦИИ ВЕБ-АВТОРИЗАЦИИ (ТОЛЬКО ДЛЯ CODE)
# =========================
@dp.message(Command("simulate_auth"))
@rate_limit()
@safe_send_message
async def cmd_simulate_auth(message: Message):
    """Имитация авторизации через веб-клиент (только для Code)"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if not user or user.get("status") != UserStatus.ANONYMOUS:
        await message.answer("❌ <b>Нет ожидающей авторизации</b>\n\nСначала используйте /login и выберите Code.")
        return

    login_token = user.get("login_token")
    if not login_token:
        await message.answer("❌ <b>Ошибка: токен входа не найден</b>")
        return

    # Определяем роль из данных пользователя
    role = "student"  # по умолчанию

    # Имитируем авторизацию через веб-клиент
    result = await auth_service.simulate_web_client_auth(login_token, role)

    if result:
        await message.answer(
            "✅ <b>Имитация веб-авторизации успешна!</b>\n\nТеперь нажмите 'Проверить статус' или подождите несколько секунд.")
    else:
        await message.answer("❌ <b>Ошибка имитации авторизации</b>\n\nВозможно, код устарел или токен не найден.")


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

    # Простой ответ
    await message.answer("🏓 <b>Pong!</b>")

    end_time = datetime.utcnow()
    response_time = (end_time - start_time).total_seconds() * 1000

    # Отправляем время ответа
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
    text += f"<b>Сервис авторизации:</b> {AUTH_SERVICE_URL}\n"
    text += f"<b>Режим авторизации:</b> {'Реальный сервис' if auth_service.real_service and auth_service.real_service.use_real_service else 'Заглушка'}\n"

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

    text += "🔐 <b>Сервис авторизации:</b>\n"
    text += f"  • <b>URL:</b> {AUTH_SERVICE_URL}\n"
    text += f"  • <b>Режим:</b> {'🟢 Реальный сервис' if auth_service.real_service and auth_service.real_service.use_real_service else '⚠️ Заглушка'}\n\n"

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
    text += f"🔐 <b>Сервис авторизации:</b> {'🟢 Реальный сервис' if auth_service.real_service and auth_service.real_service.use_real_service else '⚠️ Заглушка'}\n"

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
# КОМАНДА ALL_COURSES (ВСЕ КУРСЫ)
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
            teacher = data_storage.users.get(course.get('teacher_id', 0))
            teacher_name = teacher.get('full_name', 'Неизвестно') if teacher else 'Неизвестно'

            text += f"🎓 <b>{course.get('name', 'Без названия')}</b> (ID: {course.get('id', '?')})\n"
            text += f"   📝 Описание: {course.get('description', 'Нет описания')}\n"
            text += f"   👨‍🏫 Преподаватель: {teacher_name}\n"
            text += f"   📊 Статус: {'🟢 Активен' if course.get('is_active', True) else '🔴 Неактивен'}\n\n"

        if len(courses) > 10:
            text += f"\n... и еще {len(courses) - 10} курсов"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении курсов: {e}")
        await message.answer(f"❌ <b>Ошибка при получении курсов:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА USERS (СПИСОК ПОЛЬЗОВАТЕЛЕЙ)
# =========================
@dp.message(Command("users"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_users(message: Message, user: Dict):
    """Получить список пользователей"""
    api_token = user.get("api_token", "")

    try:
        users_list = await api_client.get_users(api_token)

        if not users_list:
            await message.answer("👥 <b>Нет пользователей в системе</b>")
            return

        text = "👥 <b>Список пользователей:</b>\n\n"
        for user_data in users_list[:15]:  # Ограничиваем вывод 15 пользователями
            role = user_data.get('role', 'student')
            role_emoji = "👨‍🏫" if role == "teacher" else "👨‍🎓"
            blocked = "🔴" if user_data.get('is_blocked', False) else "🟢"

            text += f"{role_emoji} <b>{user_data.get('full_name', 'Без имени')}</b> (ID: {user_data.get('id', '?')})\n"
            text += f"   📧 Email: {user_data.get('email', 'Нет email')}\n"
            text += f"   🎭 Роль: {role} | Статус: {blocked}\n\n"

        if len(users_list) > 15:
            text += f"\n... и еще {len(users_list) - 15} пользователей"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении пользователей: {e}")
        await message.answer(f"❌ <b>Ошибка при получении пользователей:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА USER_INFO (ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ)
# =========================
@dp.message(Command("user_info"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_user_info(message: Message, user: Dict):
    """Получить информацию о пользователе"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer("ℹ️ <b>Использование:</b> <code>/user_info ID_пользователя</code>")
        return

    try:
        user_id = int(args[1])
        api_token = user.get("api_token", "")

        user_info = await api_client.get_user_info(api_token, user_id)

        if not user_info or 'error' in user_info:
            await message.answer(f"❌ <b>Пользователь с ID {user_id} не найден</b>")
            return

        role = user_info.get('role', 'student')
        role_emoji = "👨‍🏫" if role == "teacher" else "👨‍🎓"
        blocked = "🔴 Заблокирован" if user_info.get('is_blocked', False) else "🟢 Активен"

        text = f"{role_emoji} <b>Информация о пользователе</b>\n\n"
        text += f"<b>ID:</b> {user_info.get('id', '?')}\n"
        text += f"<b>ФИО:</b> {user_info.get('full_name', 'Неизвестно')}\n"
        text += f"<b>Email:</b> {user_info.get('email', 'Неизвестно')}\n"
        text += f"<b>Роль:</b> {role}\n"
        text += f"<b>Статус:</b> {blocked}\n"

        # Получаем курсы пользователя
        user_data = await api_client.get_user_courses_grades(api_token, user_id)
        courses = user_data.get('courses', [])
        attempts = user_data.get('attempts', [])

        text += f"\n<b>Курсы ({len(courses)}):</b>\n"
        if courses:
            for course in courses[:5]:  # Показываем только первые 5 курсов
                text += f"  • {course.get('name', 'Без названия')} (ID: {course.get('id', '?')})\n"
            if len(courses) > 5:
                text += f"  • ... и еще {len(courses) - 5} курсов\n"
        else:
            text += "  Нет курсов\n"

        text += f"\n<b>Попытки тестирования ({len(attempts)}):</b>\n"
        if attempts:
            completed = [a for a in attempts if a.get('status') == 'completed']
            in_progress = [a for a in attempts if a.get('status') == 'in_progress']

            text += f"  Завершено: {len(completed)}\n"
            text += f"  В процессе: {len(in_progress)}\n"

            if completed:
                avg_score = sum(a.get('score', 0) for a in completed) / len(completed)
                text += f"  Средний балл: {avg_score:.1f}%\n"
        else:
            text += "  Нет попыток\n"

        await message.answer(text)
    except ValueError:
        await message.answer("❌ <b>Неверный ID пользователя</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пользователе: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА UPDATE_FULLNAME (ИЗМЕНЕНИЕ ФИО)
# =========================
@dp.message(Command("update_fullname"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_update_fullname(message: Message, user: Dict):
    """Изменить ФИО пользователя"""
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/update_fullname ID_пользователя ФИО</code>\n\nПример: <code>/update_fullname 1 Иванов Иван Иванович</code>")
        return

    try:
        target_id = int(args[1])
        full_name = args[2]

        # Проверяем права: пользователь может менять только свое ФИО, если он не преподаватель
        current_user_id = user.get("user_id")
        current_role = user.get("role")

        if current_role != "teacher" and target_id != current_user_id:
            await message.answer("❌ <b>Недостаточно прав</b>\n\nВы можете изменять только свое ФИО.")
            return

        api_token = user.get("api_token", "")
        result = await api_client.update_user_fullname(api_token, target_id, full_name)

        if 'error' in result:
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
        else:
            await message.answer(f"✅ <b>ФИО обновлено</b>\n\nПользователь {target_id}: {full_name}")
    except ValueError:
        await message.answer("❌ <b>Неверный ID пользователя</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при изменении ФИО: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА BLOCK_USER (БЛОКИРОВКА ПОЛЬЗОВАТЕЛЯ)
# =========================
@dp.message(Command("block_user"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_block_user(message: Message, user: Dict):
    """Заблокировать/разблокировать пользователя"""
    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/block_user ID_пользователя true/false</code>\n\nПримеры:\n<code>/block_user 1 true</code> - заблокировать\n<code>/block_user 1 false</code> - разблокировать")
        return

    try:
        target_id = int(args[1])
        block_status = args[2].lower()

        if block_status not in ['true', 'false']:
            await message.answer(
                "❌ <b>Неверный статус блокировки</b>\n\nИспользуйте 'true' для блокировки или 'false' для разблокировки.")
            return

        is_blocked = block_status == 'true'
        api_token = user.get("api_token", "")
        result = await api_client.update_user_block_status(api_token, target_id, is_blocked)

        if 'error' in result:
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
        else:
            action = "заблокирован" if is_blocked else "разблокирован"
            await message.answer(f"✅ <b>Пользователь {action}</b>\n\nПользователь {target_id} {action}.")
    except ValueError:
        await message.answer("❌ <b>Неверный ID пользователя</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при изменении статуса блокировки: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА CREATE_COURSE (СОЗДАНИЕ КУРСА)
# =========================
@dp.message(Command("create_course"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_create_course(message: Message, user: Dict):
    """Создать новый курс"""
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/create_course Название; Описание</code>\n\nПример: <code>/create_course Математика; Основы математики для начинающих</code>\n\nПримечание: название и описание разделяются точкой с запятой.")
        return

    try:
        # Разделяем название и описание по точке с запятой
        parts = args[2].split(';', 1)
        if len(parts) < 2:
            await message.answer(
                "❌ <b>Неверный формат</b>\n\nИспользуйте формат: Название; Описание\nПример: Математика; Основы математики")
            return

        name = parts[0].strip()
        description = parts[1].strip()
        teacher_id = user.get("user_id")

        api_token = user.get("api_token", "")
        result = await api_client.create_course(api_token, name, description, teacher_id)

        if 'error' in result:
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
        else:
            course_id = result.get('course_id', '?')
            await message.answer(
                f"✅ <b>Курс создан</b>\n\nНазвание: {name}\nID курса: {course_id}\nОписание: {description}")
    except Exception as e:
        logger.error(f"Ошибка при создании курса: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА COURSE_INFO (ИНФОРМАЦИЯ О КУРСЕ)
# =========================
@dp.message(Command("course_info"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_course_info(message: Message, user: Dict):
    """Получить информацию о курсе"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/course_info ID_курса</code>\n\nПример: <code>/course_info 1</code>")
        return

    try:
        course_id = int(args[1])
        api_token = user.get("api_token", "")

        course_info = await api_client.get_course_info(api_token, course_id)

        if not course_info or 'error' in course_info:
            await message.answer(f"❌ <b>Курс с ID {course_id} не найден</b>")
            return

        teacher = course_info.get('teacher', {})
        teacher_name = teacher.get('full_name', 'Неизвестно') if teacher else 'Неизвестно'

        text = "🎓 <b>Информация о курсе</b>\n\n"
        text += f"<b>ID:</b> {course_info.get('id', '?')}\n"
        text += f"<b>Название:</b> {course_info.get('name', 'Без названия')}\n"
        text += f"<b>Описание:</b> {course_info.get('description', 'Нет описания')}\n"
        text += f"<b>Преподаватель:</b> {teacher_name} (ID: {course_info.get('teacher_id', '?')})\n"
        text += f"<b>Статус:</b> {'🟢 Активен' if course_info.get('is_active', True) else '🔴 Неактивен'}\n"

        # Получаем тесты курса
        tests = await api_client.get_course_tests(api_token, course_id)
        text += f"\n<b>Тесты ({len(tests)}):</b>\n"
        if tests:
            for test in tests[:5]:  # Показываем только первые 5 тестов
                status = "🟢" if test.get('is_active', False) else "🔴"
                text += f"  {status} {test.get('name', 'Без названия')} (ID: {test.get('id', '?')})\n"
                text += f"    Вопросов: {len(test.get('questions', []))}\n"
            if len(tests) > 5:
                text += f"  ... и еще {len(tests) - 5} тестов\n"
        else:
            text += "  Нет тестов\n"

        # Получаем студентов курса (только для преподавателей)
        if user.get("role") == "teacher":
            students = await api_client.get_course_students(api_token, course_id)
            text += f"\n<b>Студенты ({len(students)}):</b>\n"
            if students:
                for student in students[:5]:  # Показываем только первых 5 студентов
                    text += f"  👨‍🎓 {student.get('full_name', 'Без имени')} (ID: {student.get('id', '?')})\n"
                if len(students) > 5:
                    text += f"  ... и еще {len(students) - 5} студентов\n"
            else:
                text += "  Нет студентов\n"

        await message.answer(text)
    except ValueError:
        await message.answer("❌ <b>Неверный ID курса</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при получении информации о курсе: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА COURSE_STUDENTS (СТУДЕНТЫ КУРСА)
# =========================
@dp.message(Command("course_students"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_course_students(message: Message, user: Dict):
    """Получить список студентов курса"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/course_students ID_курса</code>\n\nПример: <code>/course_students 1</code>")
        return

    try:
        course_id = int(args[1])
        api_token = user.get("api_token", "")

        students = await api_client.get_course_students(api_token, course_id)

        if not students:
            await message.answer(f"📚 <b>На курсе {course_id} нет студентов</b>")
            return

        text = f"👥 <b>Студенты курса {course_id}:</b>\n\n"
        for student in students[:20]:  # Ограничиваем вывод 20 студентами
            blocked = "🔴" if student.get('is_blocked', False) else "🟢"
            text += f"{blocked} <b>{student.get('full_name', 'Без имени')}</b> (ID: {student.get('id', '?')})\n"
            text += f"   📧 Email: {student.get('email', 'Нет email')}\n"
            text += f"   🎭 Роль: {student.get('role', 'student')}\n\n"

        if len(students) > 20:
            text += f"\n... и еще {len(students) - 20} студентов"

        await message.answer(text)
    except ValueError:
        await message.answer("❌ <b>Неверный ID курса</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при получении студентов курса: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА ENROLL_STUDENT (ЗАПИСАТЬ СТУДЕНТА НА КУРС)
# =========================
@dp.message(Command("enroll_student"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_enroll_student(message: Message, user: Dict):
    """Записать студента на курс"""
    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/enroll_student ID_курса ID_студента</code>\n\nПример: <code>/enroll_student 1 2</code>\n\nЗаписывает студента 2 на курс 1.")
        return

    try:
        course_id = int(args[1])
        student_id = int(args[2])
        api_token = user.get("api_token", "")

        result = await api_client.enroll_student_to_course(api_token, course_id, student_id)

        if 'error' in result:
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
        else:
            await message.answer(
                f"✅ <b>Студент записан на курс</b>\n\nСтудент {student_id} записан на курс {course_id}.")
    except ValueError:
        await message.answer("❌ <b>Неверные ID</b>\n\nID курса и ID студента должны быть числами.")
    except Exception as e:
        logger.error(f"Ошибка при записи студента на курс: {e}")
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
        for test in tests[:15]:  # Ограничиваем вывод 15 тестами
            status = "🟢 Активен" if test.get('is_active', False) else "🔴 Неактивен"
            questions = test.get('questions', [])

            text += f"🧪 <b>{test.get('name', 'Без названия')}</b> (ID: {test.get('id', '?')})\n"
            text += f"   📊 Статус: {status}\n"
            text += f"   ❓ Вопросов: {len(questions)}\n"

            if questions:
                text += f"   📋 ID вопросов: {', '.join(map(str, questions[:3]))}"
                if len(questions) > 3:
                    text += f" ... (ещё {len(questions) - 3})"
                text += "\n"
            text += "\n"

        if len(tests) > 15:
            text += f"\n... и еще {len(tests) - 15} тестов"

        await message.answer(text)
    except ValueError:
        await message.answer("❌ <b>Неверный ID курса</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при получении тестов курса: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА ADD_TEST (ДОБАВИТЬ ТЕСТ В КУРС)
# =========================
@dp.message(Command("add_test"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_add_test(message: Message, user: Dict):
    """Добавить тест в курс"""
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/add_test ID_курса; Название_теста</code>\n\nПример: <code>/add_test 1; Итоговый тест по Python</code>\n\nПримечание: ID курса и название разделяются точкой с запятой.")
        return

    try:
        # Разделяем ID курса и название теста по точке с запятой
        parts = args[2].split(';', 1)
        if len(parts) < 2:
            await message.answer(
                "❌ <b>Неверный формат</b>\n\nИспользуйте формат: ID_курса; Название_теста\nПример: 1; Итоговый тест по Python")
            return

        course_id = int(parts[0].strip())
        test_name = parts[1].strip()

        api_token = user.get("api_token", "")
        result = await api_client.add_test_to_course(api_token, course_id, test_name)

        if 'error' in result:
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
        else:
            test_id = result.get('test_id', '?')
            await message.answer(
                f"✅ <b>Тест добавлен</b>\n\nНазвание: {test_name}\nID теста: {test_id}\nКурс: {course_id}\n\nПримечание: тест по умолчанию не активен.")
    except ValueError:
        await message.answer("❌ <b>Неверный ID курса</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при добавлении теста: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА ACTIVATE_TEST (АКТИВАЦИЯ ТЕСТА)
# =========================
@dp.message(Command("activate_test"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_activate_test(message: Message, user: Dict):
    """Активировать/деактивировать тест"""
    args = message.text.split()
    if len(args) < 4:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/activate_test ID_курса ID_теста true/false</code>\n\nПримеры:\n<code>/activate_test 1 1 true</code> - активировать тест 1 курса 1\n<code>/activate_test 1 1 false</code> - деактивировать тест 1 курса 1")
        return

    try:
        course_id = int(args[1])
        test_id = int(args[2])
        activate_status = args[3].lower()

        if activate_status not in ['true', 'false']:
            await message.answer(
                "❌ <b>Неверный статус активации</b>\n\nИспользуйте 'true' для активации или 'false' для деактивации.")
            return

        is_active = activate_status == 'true'
        api_token = user.get("api_token", "")
        result = await api_client.update_test_status(api_token, course_id, test_id, is_active)

        if 'error' in result:
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
        else:
            action = "активирован" if is_active else "деактивирован"
            await message.answer(f"✅ <b>Тест {action}</b>\n\nТест {test_id} курса {course_id} {action}.")
    except ValueError:
        await message.answer("❌ <b>Неверные ID</b>\n\nID курса и ID теста должны быть числами.")
    except Exception as e:
        logger.error(f"Ошибка при изменении статуса теста: {e}")
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

        # Получаем попытки теста
        attempts = await api_client.get_test_attempts(api_token, test_id)

        if not attempts:
            await message.answer(f"📊 <b>На тесте {test_id} нет завершенных попыток</b>")
            return

        text = f"📊 <b>Результаты теста {test_id}:</b>\n\n"

        # Статистика
        total_attempts = len(attempts)
        avg_score = sum(a.get('score', 0) for a in attempts) / total_attempts if total_attempts > 0 else 0
        best_score = max(a.get('score', 0) for a in attempts) if attempts else 0
        worst_score = min(a.get('score', 0) for a in attempts) if attempts else 0

        text += f"<b>Статистика:</b>\n"
        text += f"  • Всего попыток: {total_attempts}\n"
        text += f"  • Средний балл: {avg_score:.1f}%\n"
        text += f"  • Лучший результат: {best_score}%\n"
        text += f"  • Худший результат: {worst_score}%\n\n"

        text += f"<b>Детали по студентам:</b>\n\n"
        for attempt in attempts[:10]:  # Ограничиваем вывод 10 попытками
            score = attempt.get('score', 0)
            grade = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"

            text += f"{grade} <b>{attempt.get('full_name', 'Без имени')}</b> (ID: {attempt.get('user_id', '?')})\n"
            text += f"   🎯 Балл: {score}%\n"
            text += f"   📝 ID попытки: {attempt.get('attempt_id', '?')}\n\n"

        if len(attempts) > 10:
            text += f"\n... и еще {len(attempts) - 10} попыток"

        await message.answer(text)
    except ValueError:
        await message.answer("❌ <b>Неверный ID теста</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при получении результатов теста: {e}")
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
            author = data_storage.users.get(question.get('author_id', 0))
            author_name = author.get('full_name', 'Неизвестно') if author else 'Неизвестно'

            text += f"📝 <b>{question.get('title', 'Без названия')}</b> (ID: {question.get('id', '?')})\n"
            text += f"   📄 Текст: {question.get('text', 'Нет текста')[:50]}...\n"
            text += f"   👨‍🏫 Автор: {author_name}\n"
            text += f"   🔢 Вариантов: {len(question.get('options', []))}\n"
            text += f"   ✅ Правильный: {question.get('correct', '?')}\n"
            text += f"   📚 Версия: {question.get('version', '1')}\n\n"

        if len(questions) > 10:
            text += f"\n... и еще {len(questions) - 10} вопросов"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении вопросов: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА CREATE_QUESTION (СОЗДАНИЕ ВОПРОСА)
# =========================
@dp.message(Command("create_question"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_create_question(message: Message, user: Dict):
    """Создать новый вопрос"""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/create_question Название; Текст; Вариант1|Вариант2|Вариант3; НомерПравильногоОтвета</code>\n\nПример: <code>/create_question Типы данных Python; Что такое Python?; Язык программирования|Змея|Оба варианта верны; 2</code>\n\nПримечания:\n1. Разделители: ; между полями, | между вариантами ответов\n2. Нумерация ответов с 0")
        return

    try:
        # Парсим сложную строку
        parts = args[1].split(';', 3)
        if len(parts) < 4:
            await message.answer(
                "❌ <b>Неверный формат</b>\n\nНужно 4 поля, разделенных точкой с запятой:\nНазвание; Текст; Варианты; НомерПравильногоОтвета")
            return

        title = parts[0].strip()
        text = parts[1].strip()
        options_str = parts[2].strip()
        correct_str = parts[3].strip()

        # Парсим варианты ответов
        options = [opt.strip() for opt in options_str.split('|') if opt.strip()]
        if len(options) < 2:
            await message.answer("❌ <b>Недостаточно вариантов ответа</b>\n\nНужно минимум 2 варианта ответа.")
            return

        # Парсим номер правильного ответа
        try:
            correct = int(correct_str)
            if correct < 0 or correct >= len(options):
                await message.answer(
                    f"❌ <b>Неверный номер правильного ответа</b>\n\nНомер должен быть от 0 до {len(options) - 1}.")
                return
        except ValueError:
            await message.answer("❌ <b>Неверный номер правильного ответа</b>\n\nНомер должен быть числом.")
            return

        author_id = user.get("user_id")
        api_token = user.get("api_token", "")

        result = await api_client.create_question(api_token, title, text, options, correct, author_id)

        if 'error' in result:
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
        else:
            question_id = result.get('question_id', '?')
            await message.answer(
                f"✅ <b>Вопрос создан</b>\n\nID вопроса: {question_id}\nНазвание: {title}\nВариантов: {len(options)}\nПравильный ответ: {correct}")
    except Exception as e:
        logger.error(f"Ошибка при создании вопроса: {e}")
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
        for course in courses:
            teacher = data_storage.users.get(course.get('teacher_id', 0))
            teacher_name = teacher.get('full_name', 'Неизвестно') if teacher else 'Неизвестно'

            text += f"🎓 <b>{course.get('name', 'Без названия')}</b> (ID: {course.get('id', '?')})\n"
            text += f"   📝 Описание: {course.get('description', 'Нет описания')}\n"
            text += f"   👨‍🏫 Преподаватель: {teacher_name}\n"
            text += f"   📊 Статус: {'🟢 Активен' if course.get('is_active', True) else '🔴 Неактивен'}\n\n"

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

        # Фильтруем только завершенные попытки
        completed_attempts = [a for a in attempts if a.get('status') == 'completed']

        if not completed_attempts:
            await message.answer("📊 <b>У вас нет завершенных тестов</b>")
            return

        text = "📊 <b>Ваши оценки:</b>\n\n"

        # Группируем попытки по тестам
        test_grades = {}
        for attempt in completed_attempts:
            test_id = attempt.get('test_id')
            if test_id not in test_grades:
                test_grades[test_id] = []
            test_grades[test_id].append(attempt.get('score', 0))

        # Выводим информацию по тестам
        for test_id, grades in list(test_grades.items())[:10]:  # Ограничиваем вывод 10 тестами
            test = data_storage.tests.get(test_id, {})
            test_name = test.get('name', f'Тест {test_id}')
            course_id = test.get('course_id', '?')
            course = data_storage.courses.get(course_id, {})
            course_name = course.get('name', f'Курс {course_id}')

            avg_grade = sum(grades) / len(grades) if grades else 0
            best_grade = max(grades) if grades else 0
            attempts_count = len(grades)

            text += f"🧪 <b>{test_name}</b>\n"
            text += f"   📚 Курс: {course_name}\n"
            text += f"   📈 Средний балл: {avg_grade:.1f}%\n"
            text += f"   🏆 Лучший результат: {best_grade}%\n"
            text += f"   🔢 Попыток: {attempts_count}\n\n"

        if len(test_grades) > 10:
            text += f"\n... и еще {len(test_grades) - 10} тестов"

        # Общая статистика
        total_attempts = len(completed_attempts)
        avg_score = sum(a.get('score', 0) for a in completed_attempts) / total_attempts if total_attempts > 0 else 0
        best_score = max(a.get('score', 0) for a in completed_attempts) if completed_attempts else 0

        text += f"\n<b>Общая статистика:</b>\n"
        text += f"  • Всего завершенных тестов: {total_attempts}\n"
        text += f"  • Средний балл: {avg_score:.1f}%\n"
        text += f"  • Лучший результат: {best_score}%\n"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении оценок пользователя: {e}")
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

        for attempt in attempts[:10]:  # Ограничиваем вывод 10 попытками
            test_id = attempt.get('test_id')
            test = data_storage.tests.get(test_id, {})
            test_name = test.get('name', f'Тест {test_id}')
            status = attempt.get('status', 'unknown')
            score = attempt.get('score', '?')

            status_emoji = "🟢" if status == 'completed' else "🟡" if status == 'in_progress' else "⚪"
            status_text = "Завершено" if status == 'completed' else "В процессе" if status == 'in_progress' else "Неизвестно"

            text += f"{status_emoji} <b>{test_name}</b> (ID теста: {test_id})\n"
            text += f"   📊 Статус: {status_text}\n"
            if status == 'completed':
                text += f"   🎯 Результат: {score}%\n"
            text += f"   🆔 ID попытки: {attempt.get('id', '?')}\n\n"

        if len(attempts) > 10:
            text += f"\n... и еще {len(attempts) - 10} попыток"

        # Статистика
        completed = [a for a in attempts if a.get('status') == 'completed']
        in_progress = [a for a in attempts if a.get('status') == 'in_progress']

        text += f"<b>Статистика:</b>\n"
        text += f"  • Всего попыток: {len(attempts)}\n"
        text += f"  • Завершено: {len(completed)}\n"
        text += f"  • В процессе: {len(in_progress)}\n"

        if completed:
            avg_score = sum(a.get('score', 0) for a in completed) / len(completed)
            text += f"  • Средний балл: {avg_score:.1f}%\n"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка при получении попыток пользователя: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА START_TEST (НАЧАТЬ ТЕСТ) - ИСПРАВЛЕННАЯ ВЕРСИЯ
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
        user_id = user.get("user_id")

        # Проверяем, существует ли тест и активен ли он
        test = data_storage.tests.get(test_id)
        if not test:
            await message.answer(f"❌ <b>Тест {test_id} не найден</b>")
            return

        if not test.get('is_active', False):
            await message.answer(
                f"❌ <b>Тест {test_id} не активен</b>\n\nЭтот тест временно недоступен для прохождения.")
            return

        # Проверяем, есть ли у пользователя активная попытка для этого теста
        active_attempt = None
        for attempt_id, attempt in data_storage.attempts.items():
            if (attempt["user_id"] == user_id and
                    attempt["test_id"] == test_id and
                    attempt["status"] == "in_progress"):
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
                active_attempt = attempt
                break

        if active_attempt:
            await message.answer(
                f"ℹ️ <b>У вас уже есть активная попытка для этого теста</b>\n\nID попытки: {active_attempt['id']}\nПродолжайте прохождение.")
            return

        # Создаем новую попытку
        result = await api_client.create_attempt(api_token, test_id, user_id)

        if 'error' in result:
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
        else:
            attempt_id = result.get('attempt_id')
            test_name = test.get('name', f'Тест {test_id}')

            # Получаем первый вопрос теста
            question_ids = test.get('questions', [])
            if not question_ids:
                await message.answer(f"❌ <b>В тесте нет вопросов</b>\n\nТест {test_name} не содержит вопросов.")
                return

            first_question_id = question_ids[0]
            question = data_storage.questions.get(first_question_id, {})
            question_text = question.get('text', f'Вопрос {first_question_id}')
            options = question.get('options', ['Вариант 1', 'Вариант 2', 'Вариант 3'])

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
            text += f"❓ Вопросов: {len(question_ids)}\n\n"
            text += f"📝 <b>Вопрос 1 из {len(question_ids)}:</b>\n"
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
        result = await api_client.update_attempt_answer(api_token, attempt_id, question_id, answer_index)

        if 'error' in result:
            await callback.answer(f"❌ Ошибка: {result['error']}", show_alert=True)
            return

        # Получаем информацию о попытке и тесте
        attempt = data_storage.attempts.get(attempt_id)
        if not attempt:
            await callback.answer("❌ Попытка не найдена", show_alert=True)
            return

        test_id = attempt.get('test_id')
        test = data_storage.tests.get(test_id)
        if not test:
            await callback.answer("❌ Тест не найден", show_alert=True)
            return

        question_ids = test.get('questions', [])
        current_index = question_ids.index(question_id) if question_id in question_ids else -1

        if current_index == -1 or current_index >= len(question_ids) - 1:
            # Это был последний вопрос
            await callback.message.edit_text(
                f"✅ <b>Ответ сохранен!</b>\n\n"
                f"Вы ответили на все вопросы теста.\n"
                f"Используйте команду /finish_test {attempt_id} для завершения теста.",
                reply_markup=None
            )
            await callback.answer("✅ Ответ сохранен")
            return

        # Получаем следующий вопрос
        next_question_id = question_ids[current_index + 1]
        next_question = data_storage.questions.get(next_question_id, {})
        next_question_text = next_question.get('text', f'Вопрос {next_question_id}')
        options = next_question.get('options', ['Вариант 1', 'Вариант 2', 'Вариант 3'])

        # Создаем кнопки для следующего вопроса
        buttons = []
        for i, option in enumerate(options):
            buttons.append([
                InlineKeyboardButton(
                    text=f"{i}. {option}",
                    callback_data=f"answer_{attempt_id}_{next_question_id}_{i}"
                )
            ])

        # Добавляем кнопку для пропуска вопроса
        buttons.append([
            InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"skip_{attempt_id}_{next_question_id}")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            f"✅ <b>Ответ сохранен!</b>\n\n"
            f"📝 <b>Вопрос {current_index + 2} из {len(question_ids)}:</b>\n"
            f"{next_question_text}\n\n"
            f"<b>Выберите вариант ответа:</b>",
            reply_markup=kb
        )
        await callback.answer("✅ Ответ сохранен")

    except Exception as e:
        logger.error(f"Ошибка в callback_answer: {e}")
        await callback.answer("❌ Ошибка при сохранении ответа", show_alert=True)


# =========================
# ОБРАБОТЧИК ДЛЯ ПРОПУСКА ВОПРОСА
# =========================
@dp.callback_query(F.data.startswith("skip_"))
async def callback_skip(callback: CallbackQuery):
    """Пропуск вопроса"""
    try:
        # Парсим данные из callback_data: skip_attemptId_questionId
        data_parts = callback.data.split("_")
        if len(data_parts) != 3:
            await callback.answer("❌ Неверный формат данных")
            return

        attempt_id = int(data_parts[1])
        question_id = int(data_parts[2])

        # Получаем пользователя
        chat_id = callback.from_user.id
        user = await get_user(chat_id)

        if not user or user.get("status") != UserStatus.AUTHORIZED:
            await callback.answer("❌ Требуется авторизация", show_alert=True)
            return

        api_token = user.get("api_token", "")

        # Сохраняем ответ как пропущенный (-1)
        result = await api_client.update_attempt_answer(api_token, attempt_id, question_id, -1)

        if 'error' in result:
            await callback.answer(f"❌ Ошибка: {result['error']}", show_alert=True)
            return

        # Получаем информацию о попытке и тесте
        attempt = data_storage.attempts.get(attempt_id)
        if not attempt:
            await callback.answer("❌ Попытка не найдена", show_alert=True)
            return

        test_id = attempt.get('test_id')
        test = data_storage.tests.get(test_id)
        if not test:
            await callback.answer("❌ Тест не найден", show_alert=True)
            return

        question_ids = test.get('questions', [])
        current_index = question_ids.index(question_id) if question_id in question_ids else -1

        if current_index == -1 or current_index >= len(question_ids) - 1:
            # Это был последний вопрос
            await callback.message.edit_text(
                f"⏭️ <b>Вопрос пропущен!</b>\n\n"
                f"Вы ответили на все вопросы теста.\n"
                f"Используйте команду /finish_test {attempt_id} для завершения теста.",
                reply_markup=None
            )
            await callback.answer("⏭️ Вопрос пропущен")
            return

        # Получаем следующий вопрос
        next_question_id = question_ids[current_index + 1]
        next_question = data_storage.questions.get(next_question_id, {})
        next_question_text = next_question.get('text', f'Вопрос {next_question_id}')
        options = next_question.get('options', ['Вариант 1', 'Вариант 2', 'Вариант 3'])

        # Создаем кнопки для следующего вопроса
        buttons = []
        for i, option in enumerate(options):
            buttons.append([
                InlineKeyboardButton(
                    text=f"{i}. {option}",
                    callback_data=f"answer_{attempt_id}_{next_question_id}_{i}"
                )
            ])

        # Добавляем кнопку для пропуска вопроса
        buttons.append([
            InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"skip_{attempt_id}_{next_question_id}")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            f"⏭️ <b>Вопрос пропущен!</b>\n\n"
            f"📝 <b>Вопрос {current_index + 2} из {len(question_ids)}:</b>\n"
            f"{next_question_text}\n\n"
            f"<b>Выберите вариант ответа:</b>",
            reply_markup=kb
        )
        await callback.answer("⏭️ Вопрос пропущен")

    except Exception as e:
        logger.error(f"Ошибка в callback_skip: {e}")
        await callback.answer("❌ Ошибка при пропуске вопроса", show_alert=True)


# =========================
# КОМАНДА ANSWER (ОТВЕТ НА ВОПРОС)
# =========================
@dp.message(Command("answer"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_answer(message: Message, user: Dict):
    """Ответить на вопрос в тесте"""
    args = message.text.split()
    if len(args) < 4:
        await message.answer(
            "ℹ️ <b>Использование:</b> <code>/answer ID_попытки ID_вопроса Номер_ответа</code>\n\nПример: <code>/answer 1001 1 0</code>\n\nПримечание: нумерация ответов с 0")
        return

    try:
        attempt_id = int(args[1])
        question_id = int(args[2])
        answer_index = int(args[3])

        api_token = user.get("api_token", "")

        # Проверяем, что попытка принадлежит пользователю
        attempt = data_storage.attempts.get(attempt_id)
        if not attempt or attempt.get('user_id') != user.get('user_id'):
            await message.answer("❌ <b>Попытка не найдена или не принадлежит вам</b>")
            return

        # Проверяем статус попытки
        if attempt.get('status') != 'in_progress':
            await message.answer(
                "❌ <b>Попытка уже завершена</b>\n\nВы не можете отвечать на вопросы в завершенной попытке.")
            return

        result = await api_client.update_attempt_answer(api_token, attempt_id, question_id, answer_index)

        if 'error' in result:
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
        else:
            # Получаем информацию о вопросе
            question = data_storage.questions.get(question_id, {})
            options = question.get('options', [])
            answer_text = options[answer_index] if answer_index < len(options) else f"Вариант {answer_index}"

            await message.answer(
                f"✅ <b>Ответ сохранен</b>\n\nВопрос: {question_id}\nОтвет: {answer_text}\nПопытка: {attempt_id}")
    except ValueError:
        await message.answer("❌ <b>Неверные параметры</b>\n\nВсе параметры должны быть числами.")
    except Exception as e:
        logger.error(f"Ошибка при сохранении ответа: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n\n{str(e)[:200]}...")


# =========================
# КОМАНДА FINISH_TEST (ЗАВЕРШИТЬ ТЕСТ)
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

        # Проверяем, что попытка принадлежит пользователю
        attempt = data_storage.attempts.get(attempt_id)
        if not attempt or attempt.get('user_id') != user.get('user_id'):
            await message.answer("❌ <b>Попытка не найдена или не принадлежит вам</b>")
            return

        # Проверяем статус попытки
        if attempt.get('status') != 'in_progress':
            await message.answer(f"ℹ️ <b>Попытка уже завершена</b>\n\nРезультат: {attempt.get('score', '?')}%")
            return

        result = await api_client.complete_attempt(api_token, attempt_id)

        if 'error' in result:
            await message.answer(f"❌ <b>Ошибка:</b> {result['error']}")
        else:
            score = result.get('score', 0)
            test_id = attempt.get('test_id')
            test = data_storage.tests.get(test_id, {})
            test_name = test.get('name', f'Тест {test_id}')

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
            text += f"🧪 Тест: {test_name}\n"
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
# ОБНОВЛЕННАЯ КОМАНДА HELP (ОБЩАЯ) - ДОСТУПНА ВСЕМ
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

<b>Управление пользователями:</b>
/users — список пользователей
/user_info ID — информация о пользователе
/update_fullname ID ФИО — изменить ФИО
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
/create_question Название; Текст; Варианты; НомерПравильногоОтвета — создать вопрос

<b>Специальные справки:</b>
/help_teacher — подробная справка для преподавателей
/help_test — команды для тестировщиков

<b>Быстрые команды:</b>
/tests — список тестов
/debug — отладочная информация
/services — информация о сервисах
/ping — проверка работы бота
/echo — эхо-команда
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
/answer ID_попытки ID_вопроса Номер_ответа — ответить на вопрос
/finish_test ID_попытки — завершить тест

<b>Мои данные:</b>
/my_courses — мои курсы
/my_grades — мои оценки
/my_attempts — мои попытки

<b>Специальные справки:</b>
/help_student — подробная справка для студентов
/help_test — команды для тестировщиков

<b>Быстрые команды:</b>
/ping — проверка работы бота
/echo — эхо-команда
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

<b>Тестирование:</b>
/help_test — команды для тестировщиков

<b>Технические команды:</b>
/services — информация о сервисах
/debug — отладочная информация
/ping — проверка работы бота
/echo — эхо-команда
"""

    await message.answer(help_text)


# =========================
# КОМАНДА HELP_STUDENT - ТОЛЬКО ДЛЯ АВТОРИЗОВАННЫХ СТУДЕНТОВ
# =========================
@dp.message(Command("help_student"))
@rate_limit()
@require_auth()
@require_role("student")
@safe_send_message
async def cmd_help_student(message: Message, user: Dict):
    help_text = """
👨‍🎓 <b>Справка по командам для студентов</b>

<b>Основные команды:</b>
/tests — список доступных тестов
/start_test ID_теста — начать тест
/profile — ваш профиль
/status — статус системы
/logout — выход из системы
/logout_all — выход на всех устройствах

<b>Мои данные:</b>
/my_courses — мои курсы
/my_grades — мои оценки
/my_attempts — мои попытки

<b>Тестирование:</b>
• Используйте /tests для просмотра доступных тестов
• Нажмите кнопку "Начать тест" или используйте /start_test ID
• Отвечайте на вопросы, выбирая варианты ответов
• Результат появится автоматически после завершения

<b>Прохождение теста:</b>
1. Выберите тест из списка /tests
2. Нажмите "Начать тест" или используйте /start_test ID
3. Отвечайте на вопросы последовательно
4. По завершении увидите свой результат

<b>Полезные команды:</b>
/services — информация о сервисах
/debug — отладочная информация
/ping — проверка работы бота
/echo — эхо-команда
"""

    await message.answer(help_text)


# =========================
# КОМАНДА HELP_TEACHER - ТОЛЬКО ДЛЯ АВТОРИЗОВАННЫХ ПРЕПОДАВАТЕЛЕЙ
# =========================
@dp.message(Command("help_teacher"))
@rate_limit()
@require_auth()
@require_role("teacher")
@safe_send_message
async def cmd_help_teacher(message: Message, user: Dict):
    help_text = """
👨‍🏫 <b>Справка по командам для преподавателей</b>

<b>Основные команды:</b>
/users — список пользователей
/user_info [ID] — информация о пользователе
/update_fullname ID ФИО — изменить ФИО
/block_user ID true/false — блокировка/разблокировка
/status — статус системы
/logout — выход из системы
/logout_all — выход на всех устройствах

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

<b>Примеры использования:</b>
• Создать курс: /create_course Математика; Основы математики
• Добавить тест: /add_test 1; Итоговый тест по математике
• Просмотреть студентов: /course_students 1
• Проверить результаты: /test_results 1

<b>Технические команды:</b>
/services — информация о сервисах
/debug — отладочная информация
/ping — проверка работы бота
/echo — эхо-команда
"""

    await message.answer(help_text)


# =========================
# КОМАНДА HELP_TEST - ДОСТУПНА ВСЕМ ДЛЯ ТЕСТИРОВАНИЯ
# =========================
@dp.message(Command("help_test"))
@rate_limit()
@safe_send_message
async def cmd_help_test(message: Message):
    help_text = """
🧪 <b>Команды для тестировщиков</b>

<b>Автоматическая авторизация:</b>
/auth_student — авторизоваться как студент (без ввода кода)
/auth_teacher — авторизоваться как преподаватель (без ввода кода)

<b>Тестирование авторизации через Code:</b>
/simulate_auth — имитировать веб-авторизацию (только для ожидающих авторизации через Code)

<b>Тестирование системы:</b>
/tests — список тестов (требует авторизации)
/profile — профиль пользователя (требует авторизации)
/status — статус системы

<b>Отладка:</b>
/debug — отладочная информация
/services — информация о сервисах
/ping — проверка работы бота
/echo — эхо-команда

<b>Пример использования:</b>
1. Используйте /auth_student для быстрой авторизации как студент
2. Используйте /tests для просмотра доступных тестов
3. Используйте /start_test 1 для начала теста
4. Используйте /logout для выхода
"""

    await message.answer(help_text)


# =========================
# КОМАНДА ДЛЯ АВТОМАТИЧЕСКОЙ АВТОРИЗАЦИИ СТУДЕНТА
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
    user_id = 2
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
# КОМАНДА ДЛЯ АВТОМАТИЧЕСКОЙ АВТОРИЗАЦИИ ПРЕПОДАВАТЕЛЯ
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
    user_id = 1
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

<b>Сессия в Telegram:</b>
🤖 <b>Авторизован:</b> {auth_date}
🔐 <b>Статус:</b> {'🔴 Заблокирован' if user_info.get('is_blocked') else '🟢 Активен'}
"""

    await message.answer(text)


# =========================
# ОБНОВЛЕННАЯ КОМАНДА TESTS (без кнопок)
# =========================
@dp.message(Command("tests"))
@rate_limit()
@require_auth()
@safe_send_message
async def cmd_tests(message: Message, user: Dict):
    """Список доступных тестов (простой список, без кнопок)"""
    api_token = user.get("api_token", "")

    try:
        # Используем локальное хранилище для тестов
        tests = [test for test in data_storage.tests.values() if test["is_active"]]

        if not tests:
            await message.answer(
                "📚 <b>Нет доступных тестов</b>\n\nНа данный момент нет активных тестов для прохождения.")
            return

        text = "📚 <b>Доступные тесты:</b>\n\n"

        for test in tests:
            test_id = test.get("id", "?")
            test_name = test.get("name", f"Тест {test_id}")
            question_ids = test.get("questions", [])
            course_id = test.get("course_id", "?")
            course = data_storage.courses.get(course_id, {})
            course_name = course.get("name", f"Курс {course_id}")

            text += f"🧪 <b>{test_name}</b> (ID: {test_id})\n"
            text += f"   📚 Курс: {course_name}\n"
            text += f"   ❓ Вопросов: {len(question_ids)}\n"
            text += f"   🚀 Команда: /start_test {test_id}\n\n"

        text += "\n<b>Чтобы начать тест, используйте команду:</b>\n"
        text += "<code>/start_test ID_теста</code>\n\n"
        text += "<b>Пример:</b>\n"
        text += "<code>/start_test 1</code> - начать тест с ID 1"

        await message.answer(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Ошибка при получении тестов: {e}")
        await message.answer(f"❌ <b>Ошибка при загрузке тестов:</b>\n\n{str(e)[:200]}...")


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


# ========================
# ОСНОВНАЯ ФУНКЦИЯ
# =========================
async def main():
    logger.info("🤖 Telegram bot starting...")
    logger.info(f"📡 API Base URL: {API_BASE_URL}")
    logger.info(f"🔐 Auth Service URL: {AUTH_SERVICE_URL}")
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