import asyncio
import logging
import os
import json
import secrets
import jwt
import aiohttp
from aiohttp import web
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
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
TESTING_PORT = int(os.getenv("TESTING_PORT", "8081"))

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
        self.test_requests = 0
        self.successful_tests = 0
        self.failed_tests = 0

    def increment_commands(self):
        self.commands_count += 1

    def add_active_user(self, user_id: int):
        self.active_users.add(user_id)

    def remove_active_user(self, user_id: int):
        self.active_users.discard(user_id)

    def get_active_users_count(self):
        return len(self.active_users)

    def increment_test_requests(self):
        self.test_requests += 1

    def increment_successful_tests(self):
        self.successful_tests += 1

    def increment_failed_tests(self):
        self.failed_tests += 1


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
# DATA STORAGE (для тестовых данных)
# =========================
class DataStorage:
    def __init__(self):
        self.users = {
            1: {"id": 1, "full_name": "Иванов Иван Иванович", "email": "teacher@example.com",
                "role": "teacher", "is_blocked": False, "created_at": "2024-01-01T10:00:00Z"},
            2: {"id": 2, "full_name": "Петров Петр Петрович", "email": "student1@example.com",
                "role": "student", "is_blocked": False, "created_at": "2024-01-02T11:00:00Z"},
        }

        self.courses = {
            1: {"id": 1, "name": "Программирование на Python",
                "description": "Основы программирования на Python",
                "teacher_id": 1, "is_active": True, "created_at": "2024-01-10T10:00:00Z"},
        }

        self.tests = {
            1: {"id": 1, "name": "Тест по основам Python", "course_id": 1,
                "is_active": True, "questions": [1, 2, 3], "created_at": "2024-02-01T10:00:00Z"},
        }

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
        }


data_storage = DataStorage()


# =========================
# API CLIENT - ДЛЯ ВЗАИМОДЕЙСТВИЯ С ВНЕШНИМ API
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

    async def get_tests(self, token: str, course_id: int = DEFAULT_COURSE_ID) -> List[Dict]:
        """Получить список тестов курса"""
        try:
            logger.info(f"📚 Запрос тестов для курса {course_id}")
            response = await self.request("GET", f"/course/tests?course_id={course_id}", token)

            if isinstance(response, dict) and "text" in response:
                try:
                    parsed = json.loads(response["text"])
                    if isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict):
                        return parsed.get("tests", [])
                except Exception as e:
                    logger.error(f"📚 Ошибка парсинга текста: {e}")
                    return []

            if isinstance(response, list):
                return response

            if isinstance(response, dict):
                tests = response.get("tests", []) or response.get("data", []) or []
                return tests if isinstance(tests, list) else []

            return []

        except Exception as e:
            logger.error(f"📚 Ошибка при получении тестов: {e}")
            # Используем локальные данные если API недоступно
            return [test for test in data_storage.tests.values() if test["course_id"] == course_id]


api_client = APIClient(API_BASE_URL, JWT_SECRET)


# =========================
# TESTING MODULE - ДЛЯ ВЗАИМОДЕЙСТВИЯ С GO-ТЕСТАМИ
# =========================
class TestingModule:
    """Модуль для обработки запросов от Go-тестировщика"""

    def __init__(self):
        self.test_results = {}
        self.test_counter = 0

    async def process_test_request(self, data: Dict) -> Dict:
        """Обработка тестового запроса от Go"""
        stats.increment_test_requests()
        self.test_counter += 1
        test_id = self.test_counter

        try:
            test_type = data.get("type", "unknown")
            endpoint = data.get("endpoint", "")
            method = data.get("method", "GET")
            token = data.get("token", "")
            params = data.get("params", {})

            logger.info(f"🧪 Тестовый запрос #{test_id}: {method} {endpoint}")

            if test_type == "health_check":
                result = await self.health_check_test()
            elif test_type == "course_tests":
                result = await self.course_tests_test(token, params)
            elif test_type == "question_list":
                result = await self.question_list_test(token, params)
            elif test_type == "custom_request":
                result = await self.custom_request_test(method, endpoint, token, params)
            else:
                result = {"error": f"Unknown test type: {test_type}"}

            self.test_results[test_id] = {
                "test_id": test_id,
                "type": test_type,
                "endpoint": endpoint,
                "method": method,
                "result": result,
                "timestamp": datetime.utcnow().isoformat(),
                "success": "error" not in result
            }

            if "error" not in result:
                stats.increment_successful_tests()
                return {
                    "test_id": test_id,
                    "status": "success",
                    "result": result
                }
            else:
                stats.increment_failed_tests()
                return {
                    "test_id": test_id,
                    "status": "error",
                    "error": result.get("error", "Unknown error")
                }

        except Exception as e:
            stats.increment_failed_tests()
            logger.error(f"❌ Ошибка в тестовом запросе: {e}")
            return {
                "test_id": test_id,
                "status": "error",
                "error": str(e)
            }

    async def health_check_test(self) -> Dict:
        """Тест health-check эндпоинта"""
        try:
            response = await api_client.request("GET", "/health", None)
            return {
                "message": "Health check completed",
                "response": response
            }
        except Exception as e:
            return {"error": f"Health check failed: {str(e)}"}

    async def course_tests_test(self, token: str, params: Dict) -> Dict:
        """Тест получения тестов курса"""
        try:
            course_id = params.get("course_id", DEFAULT_COURSE_ID)
            tests = await api_client.get_tests(token, course_id)

            return {
                "message": f"Retrieved tests for course {course_id}",
                "course_id": course_id,
                "tests_count": len(tests),
                "tests": tests[:5] if tests else []  # Ограничиваем вывод
            }
        except Exception as e:
            return {"error": f"Failed to get course tests: {str(e)}"}

    async def question_list_test(self, token: str, params: Dict) -> Dict:
        """Тест получения списка вопросов"""
        try:
            course_id = params.get("course_id", DEFAULT_COURSE_ID)
            # Используем локальные данные для вопросов
            questions = list(data_storage.questions.values())

            return {
                "message": f"Retrieved questions",
                "questions_count": len(questions),
                "questions": questions[:5] if questions else []
            }
        except Exception as e:
            return {"error": f"Failed to get questions: {str(e)}"}

    async def custom_request_test(self, method: str, endpoint: str, token: str, params: Dict) -> Dict:
        """Кастомный тестовый запрос"""
        try:
            response = await api_client.request(method, endpoint, token, params)
            return {
                "message": f"Custom request {method} {endpoint} completed",
                "response": response
            }
        except Exception as e:
            return {"error": f"Custom request failed: {str(e)}"}

    async def get_test_results(self, test_id: Optional[int] = None) -> Dict:
        """Получить результаты тестов"""
        if test_id:
            if test_id in self.test_results:
                return self.test_results[test_id]
            return {"error": f"Test {test_id} not found"}

        return {
            "total_tests": self.test_counter,
            "successful_tests": stats.successful_tests,
            "failed_tests": stats.failed_tests,
            "recent_tests": list(self.test_results.values())[-10:]  # Последние 10 тестов
        }


testing_module = TestingModule()


# =========================
# HTTP SERVER для тестирования
# =========================
async def testing_handler(request):
    """Обработчик тестовых запросов"""
    try:
        data = await request.json()

        if "type" not in data:
            return web.json_response({
                "status": "error",
                "error": "Missing 'type' field in request"
            }, status=400)

        result = await testing_module.process_test_request(data)
        return web.json_response(result)

    except json.JSONDecodeError:
        return web.json_response({
            "status": "error",
            "error": "Invalid JSON format"
        }, status=400)
    except Exception as e:
        logger.error(f"Ошибка в обработчике тестирования: {e}")
        return web.json_response({
            "status": "error",
            "error": str(e)
        }, status=500)


async def test_results_handler(request):
    """Обработчик для получения результатов тестов"""
    try:
        test_id = request.query.get("test_id")
        if test_id:
            try:
                test_id_int = int(test_id)
                results = await testing_module.get_test_results(test_id_int)
            except ValueError:
                return web.json_response({
                    "status": "error",
                    "error": "Invalid test_id format"
                }, status=400)
        else:
            results = await testing_module.get_test_results()

        return web.json_response({
            "status": "success",
            "results": results
        })

    except Exception as e:
        logger.error(f"Ошибка при получении результатов тестов: {e}")
        return web.json_response({
            "status": "error",
            "error": str(e)
        }, status=500)


async def testing_health_handler(request):
    """Health check для тестового сервера"""
    return web.json_response({
        "status": "healthy",
        "service": "telegram-bot-testing",
        "timestamp": datetime.utcnow().isoformat(),
        "test_stats": {
            "total_tests": testing_module.test_counter,
            "successful": stats.successful_tests,
            "failed": stats.failed_tests
        }
    })


async def start_testing_server():
    """Запуск сервера для тестирования"""
    app = web.Application()

    # Тестовые эндпоинты
    app.router.add_post('/test', testing_handler)
    app.router.add_get('/test/results', test_results_handler)
    app.router.add_get('/test/health', testing_health_handler)

    # Информационная страница
    async def testing_info_handler(request):
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Telegram Bot Testing API</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                .endpoint {{ background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }}
                code {{ background: #e0e0e0; padding: 2px 5px; border-radius: 3px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🧪 Telegram Bot Testing API</h1>
                <p>Этот сервер используется для тестирования функциональности Telegram-бота.</p>

                <h2>Доступные эндпоинты:</h2>

                <div class="endpoint">
                    <h3>POST /test</h3>
                    <p>Выполнить тестовый запрос</p>
                    <p><strong>Пример запроса:</strong></p>
                    <pre><code>{{
    "type": "health_check",
    "method": "GET",
    "endpoint": "/health",
    "token": "jwt_token_here",
    "params": {{}}
}}</code></pre>
                </div>

                <div class="endpoint">
                    <h3>GET /test/results</h3>
                    <p>Получить результаты тестов</p>
                    <p><strong>Параметры:</strong></p>
                    <ul>
                        <li><code>test_id</code> - ID конкретного теста (опционально)</li>
                    </ul>
                </div>

                <div class="endpoint">
                    <h3>GET /test/health</h3>
                    <p>Проверка здоровья тестового сервера</p>
                </div>

                <h2>Типы тестов:</h2>
                <ul>
                    <li><code>health_check</code> - Проверка доступности API</li>
                    <li><code>course_tests</code> - Получение тестов курса</li>
                    <li><code>question_list</code> - Получение списка вопросов</li>
                    <li><code>custom_request</code> - Произвольный HTTP запрос</li>
                </ul>

                <h2>Статистика:</h2>
                <p>Всего тестов: {testing_module.test_counter}</p>
                <p>Успешных: {stats.successful_tests}</p>
                <p>Неудачных: {stats.failed_tests}</p>

                <p><strong>Время (МСК):</strong> {format_moscow_time()}</p>
            </div>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')

    app.router.add_get('/', testing_info_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', TESTING_PORT)
    await site.start()

    logger.info(f"🧪 Сервер тестирования запущен на порту {TESTING_PORT}")
    return runner


# =========================
# HTTP SERVER для health-check основного бота
# =========================
async def health_check_handler(request):
    """Health check endpoint для мониторинга"""
    status = {
        "status": "healthy",
        "service": "telegram-bot",
        "timestamp": datetime.utcnow().isoformat(),
        "moscow_time": format_moscow_time(),
        "redis": "connected" if redis_client.connected else "disconnected",
        "active_users": stats.get_active_users_count(),
        "commands_processed": stats.commands_count,
        "testing_stats": {
            "total_requests": stats.test_requests,
            "successful_tests": stats.successful_tests,
            "failed_tests": stats.failed_tests
        }
    }
    return web.json_response(status)


async def start_http_server():
    """Запуск HTTP сервера для health-check"""
    app = web.Application()
    app.router.add_get('/health', health_check_handler)
    app.router.add_get('/status', health_check_handler)

    # Информационная страница
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
                .testing {{ background-color: #e2e3e5; color: #383d41; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 Telegram Test Bot</h1>

                <div class="status healthy">
                    <h3>Статус системы</h3>
                    <p><strong>Redis:</strong> {'🟢 Подключен' if redis_client.connected else '🔴 Отключен'}</p>
                    <p><strong>Активных пользователей:</strong> {stats.get_active_users_count()}</p>
                    <p><strong>Обработано команд:</strong> {stats.commands_count}</p>
                    <p><strong>Время (Москва):</strong> {format_moscow_time()}</p>
                    <p><strong>API URL:</strong> {API_BASE_URL}</p>
                </div>

                <div class="status testing">
                    <h3>🧪 Тестирование</h3>
                    <p><strong>Тестовых запросов:</strong> {stats.test_requests}</p>
                    <p><strong>Успешных тестов:</strong> {stats.successful_tests}</p>
                    <p><strong>Неудачных тестов:</strong> {stats.failed_tests}</p>
                    <p><strong>Тестовый сервер:</strong> <a href="http://localhost:{TESTING_PORT}">http://localhost:{TESTING_PORT}</a></p>
                </div>

                <h3>API Endpoints</h3>
                <ul>
                    <li><a href="/health">/health</a> - Health check (JSON)</li>
                    <li><a href="/status">/status</a> - Статус системы (JSON)</li>
                    <li><a href="http://localhost:{TESTING_PORT}">Тестовый сервер (порт {TESTING_PORT})</a></li>
                </ul>

                <h3>Telegram Bot</h3>
                <p>Бот работает в режиме polling. Для использования найдите бота в Telegram.</p>
                <p><strong>Основные команды:</strong> /start, /login, /tests, /status</p>
                <p><strong>Тестовые команды:</strong> /auth_student, /auth_teacher, /help_test</p>
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
# КОМАНДЫ ДЛЯ ТЕСТИРОВАНИЯ (упрощенные)
# =========================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(f"""
👋 <b>Добро пожаловать, {message.from_user.first_name or 'пользователь'}!</b>

🤖 <b>Telegram-клиент системы тестирования</b>

<b>Для тестирования используйте:</b>
/auth_student - авторизация как студент
/auth_teacher - авторизация как преподаватель
/tests - список тестов
/status - статус системы

<b>Для помощи:</b>
/help_test - команды для тестирования
""")


@dp.message(Command("auth_student"))
async def cmd_auth_student(message: Message):
    """Автоматическая авторизация как студент"""
    chat_id = message.chat.id

    # Генерируем JWT токен для студента
    payload = {
        "user_id": 2,
        "role": "student",
        "permissions": ["course:testList", "course:test:read", "answer.read", "answer.update", "answer.del"],
        "exp": datetime.utcnow() + timedelta(hours=24),
        "is_blocked": False
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    # Сохраняем пользователя
    await redis_client.setex(f"user:{chat_id}", 86400, json.dumps({
        "status": UserStatus.AUTHORIZED,
        "api_token": token,
        "user_id": 2,
        "email": f"student_{chat_id}@test.com",
        "role": "student",
        "permissions": payload["permissions"],
        "authorized_at": datetime.utcnow().isoformat()
    }))

    stats.add_active_user(chat_id)

    await message.answer(f"""
✅ <b>Авторизация студента успешна!</b>

Теперь вы можете использовать команды для студентов:
/tests - список тестов
/my_courses - мои курсы

<b>Ваш токен:</b>
<code>{token[:50]}...</code>

<b>Для тестирования API можно использовать этот токен в Go-модуле.</b>
""", parse_mode=ParseMode.HTML)


@dp.message(Command("auth_teacher"))
async def cmd_auth_teacher(message: Message):
    """Автоматическая авторизация как преподаватель"""
    chat_id = message.chat.id

    # Генерируем JWT токен для преподавателя
    payload = {
        "user_id": 1,
        "role": "teacher",
        "permissions": ["course:testList", "course:test:read", "course:test:write", "question:read", "question:write"],
        "exp": datetime.utcnow() + timedelta(hours=24),
        "is_blocked": False
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    # Сохраняем пользователя
    await redis_client.setex(f"user:{chat_id}", 86400, json.dumps({
        "status": UserStatus.AUTHORIZED,
        "api_token": token,
        "user_id": 1,
        "email": f"teacher_{chat_id}@test.com",
        "role": "teacher",
        "permissions": payload["permissions"],
        "authorized_at": datetime.utcnow().isoformat()
    }))

    stats.add_active_user(chat_id)

    await message.answer(f"""
✅ <b>Авторизация преподавателя успешна!</b>

Теперь вы можете использовать команды для преподавателей:
/users - список пользователей
/all_courses - все курсы

<b>Ваш токен:</b>
<code>{token[:50]}...</code>

<b>Для тестирования API можно использовать этот токен в Go-модуле.</b>
""", parse_mode=ParseMode.HTML)


@dp.message(Command("tests"))
async def cmd_tests(message: Message):
    """Список доступных тестов"""
    chat_id = message.chat.id
    user_data = await redis_client.get(f"user:{chat_id}")

    if not user_data:
        await message.answer("❌ <b>Требуется авторизация</b>\nИспользуйте /auth_student или /auth_teacher")
        return

    try:
        user = json.loads(user_data)
        token = user.get("api_token", "")

        tests = await api_client.get_tests(token, DEFAULT_COURSE_ID)

        if not tests:
            await message.answer("📚 <b>Нет доступных тестов</b>")
            return

        text = "📚 <b>Доступные тесты:</b>\n\n"
        for test in tests[:5]:  # Показываем первые 5 тестов
            text += f"🧪 <b>{test.get('name', 'Тест')}</b>\n"
            text += f"   ID: {test.get('id', '?')}\n"
            text += f"   Активен: {'✅' if test.get('is_active') else '❌'}\n"
            text += f"   Вопросов: {len(test.get('questions', []))}\n\n"

        if len(tests) > 5:
            text += f"... и еще {len(tests) - 5} тестов\n\n"

        text += "<b>Для начала теста используйте:</b>\n"
        text += f"<code>/start_test {tests[0]['id'] if tests else 1}</code>"

        await message.answer(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Ошибка при получении тестов: {e}")
        await message.answer(f"❌ <b>Ошибка:</b>\n{str(e)[:200]}")


@dp.message(Command("status"))
async def cmd_status(message: Message):
    """Статус системы"""
    text = f"""
📊 <b>Статус системы</b>

🤖 <b>Telegram Bot:</b>
• Активных пользователей: {stats.get_active_users_count()}
• Обработано команд: {stats.commands_count}

🧪 <b>Тестирование:</b>
• Тестовых запросов: {stats.test_requests}
• Успешных тестов: {stats.successful_tests}
• Неудачных тестов: {stats.failed_tests}

🌐 <b>Серверы:</b>
• Health check: http://localhost:{HTTP_PORT}/health
• Тестирование: http://localhost:{TESTING_PORT}
• API: {API_BASE_URL}

🕐 <b>Время (Москва):</b> {format_moscow_time()}
"""
    await message.answer(text)


@dp.message(Command("help_test"))
async def cmd_help_test(message: Message):
    """Команды для тестирования"""
    text = """
🧪 <b>Команды для тестирования</b>

<b>Быстрая авторизация:</b>
/auth_student - авторизоваться как студент
/auth_teacher - авторизоваться как преподаватель

<b>Основные команды:</b>
/tests - список тестов
/status - статус системы
/debug - отладочная информация

<b>Тестирование API:</b>
После авторизации используйте полученный токен в Go-модуле:
<code>go run test_module.go</code>

<b>Доступные эндпоинты для тестирования:</b>
• POST http://localhost:8081/test - выполнить тест
• GET http://localhost:8081/test/results - результаты тестов
• GET http://localhost:8081/test/health - health check
"""
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("debug"))
async def cmd_debug(message: Message):
    """Отладочная информация"""
    chat_id = message.chat.id
    user_data = await redis_client.get(f"user:{chat_id}")

    text = "🔧 <b>Отладочная информация</b>\n\n"

    if user_data:
        user = json.loads(user_data)
        text += f"<b>Статус:</b> {user.get('status')}\n"
        text += f"<b>Роль:</b> {user.get('role')}\n"
        text += f"<b>Токен (первые 50 симв.):</b>\n<code>{user.get('api_token', '')[:50]}...</code>\n\n"
    else:
        text += "❌ <b>Пользователь не авторизован</b>\n\n"

    text += f"<b>Redis подключен:</b> {'✅' if redis_client.connected else '❌'}\n"
    text += f"<b>Всего тестов:</b> {testing_module.test_counter}\n"
    text += f"<b>Последний тест ID:</b> {testing_module.test_counter if testing_module.test_counter > 0 else 'нет'}"

    await message.answer(text, parse_mode=ParseMode.HTML)


# =========================
# ОСНОВНАЯ ФУНКЦИЯ
# =========================
async def main():
    logger.info("🤖 Telegram bot starting...")
    logger.info(f"📡 API Base URL: {API_BASE_URL}")
    logger.info(f"🌐 HTTP Server порт: {HTTP_PORT}")
    logger.info(f"🧪 Testing Server порт: {TESTING_PORT}")

    await redis_client.connect()

    # Запуск основного HTTP сервера для health-check
    try:
        http_runner = await start_http_server()
        logger.info("✅ Основной HTTP сервер запущен")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска основного HTTP сервера: {e}")
        http_runner = None

    # Запуск тестового HTTP сервера
    try:
        testing_runner = await start_testing_server()
        logger.info("✅ Тестовый HTTP сервер запущен")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска тестового HTTP сервера: {e}")
        testing_runner = None

    logger.info("🚀 Bot is ready!")
    logger.info("📊 Доступны эндпоинты:")
    logger.info(f"   • http://localhost:{HTTP_PORT}/health - Health check основного бота")
    logger.info(f"   • http://localhost:{HTTP_PORT}/ - Информация о боте")
    logger.info(f"   • http://localhost:{TESTING_PORT}/ - Тестовый сервер")
    logger.info(f"   • http://localhost:{TESTING_PORT}/test - Выполнение тестов")
    logger.info(f"   • http://localhost:{TESTING_PORT}/test/results - Результаты тестов")

    try:
        await dp.start_polling(bot, skip_updates=True)
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    finally:
        await api_client.close()
        if http_runner:
            await http_runner.cleanup()
            logger.info("🌐 Основной HTTP сервер остановлен")
        if testing_runner:
            await testing_runner.cleanup()
            logger.info("🧪 Тестовый HTTP сервер остановлен")


if __name__ == "__main__":
    asyncio.run(main())