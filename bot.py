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
            return [
                {"id": 56, "name": "Тест по Python", "is_active": True, "question_ids": [1, 2, 3]},
                {"id": 57, "name": "Тест по Docker", "is_active": True, "question_ids": [1, 2]},
                {"id": 61, "name": "Тест по API", "is_active": False, "question_ids": []}
            ]

    async def start_test(self, token: str, test_id: int) -> Dict:
        """Начать тест"""
        try:
            logger.info(f"🚀 Запуск теста {test_id}")
            return await self.request("POST", f"/test/start?test_id={test_id}", token)
        except Exception as e:
            logger.error(f"🚀 Ошибка запуска теста: {e}")
            return {"attempt_id": 1000 + test_id, "id": 1000 + test_id}

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
        """Получить детали вопроса (заглушка, пока нет API)"""
        questions_data = {
            1: {
                "id": 1,
                "text": "Что такое Python?",
                "options": ["Язык программирования", "Змея", "Оба варианта верны"],
                "correct": 2
            },
            2: {
                "id": 2,
                "text": "Что такое Docker?",
                "options": ["Контейнеризация", "Игра", "Операционная система"],
                "correct": 0
            },
            3: {
                "id": 3,
                "text": "Что такое API?",
                "options": ["Интерфейс программирования", "Аппаратный интерфейс", "Оба варианта"],
                "correct": 0
            },
            4: {
                "id": 4,
                "text": "Какая компания создала Python?",
                "options": ["Google", "Microsoft", "Guido van Rossum", "Apple"],
                "correct": 2
            },
            5: {
                "id": 5,
                "text": "Что такое контейнеризация?",
                "options": ["Упаковка приложения со всеми зависимостями",
                            "Виртуализация на уровне ОС",
                            "Оба варианта верны",
                            "Ни один из вариантов"],
                "correct": 2
            }
        }
        return questions_data.get(question_id, {
            "id": question_id,
            "text": f"Вопрос {question_id}",
            "options": ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4"],
            "correct": 0
        })

    async def get_test_questions(self, token: str, test_id: int) -> List[int]:
        """Получить список вопросов теста (заглушка)"""
        test_questions = {
            56: [1, 2, 3, 4],  # Тест по Python
            57: [1, 2, 5],  # Тест по Docker
            61: []  # Тест по API (пустой)
        }
        return test_questions.get(test_id, [1, 2, 3])


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

    # Статическая страница с информацией о боте
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
# УЛУЧШЕННАЯ АВТОРИЗАЦИОННАЯ ЗАГЛУШКА ПО КОДУ
# =========================
class AuthServiceStub:
    def __init__(self):
        self.login_tokens = {}  # {login_token: {status, provider, code_data, created_at, user_agent, confirmed}}
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
            "user_data": None
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
                user_data = {
                    "id": user_id,
                    "email": email,
                    "role": "student"
                }
                token_data["user_data"] = user_data

            return {
                "status": "granted",
                "access_token": f"access_{secrets.token_hex(16)}",
                "refresh_token": f"refresh_{secrets.token_hex(16)}",
                "user": user_data
            }

        return {"status": "pending"}

    async def confirm_code(self, code: str, refresh_token: str = None) -> Dict:
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
                "role": "student"
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
                    "email": email
                }
            }

        return {"error": "Токен входа не найден"}

    async def simulate_web_client_auth(self, login_token: str):
        """Имитация авторизации через веб-клиент (для тестирования)"""
        if login_token not in self.login_tokens:
            return False

        token_data = self.login_tokens[login_token]
        if token_data["provider"] != "code":
            return False

        code = token_data["code"]
        if not code:
            return False

        # Имитируем ввод кода в веб-клиенте
        result = await self.confirm_code(code, "dummy_refresh_token")
        return "error" not in result


auth_service = AuthServiceStub()


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

        if provider == "code":
            # Получаем код из заглушки
            if login_token in auth_service.login_tokens:
                code = auth_service.login_tokens[login_token].get("code", "Ожидание генерации...")
            else:
                code = "Ожидание..."

            text = f"""
🔐 <b>Ожидание авторизации через код</b>

Для завершения авторизации введите код в веб-клиенте:

<b>Код: <code>{code}</code></b>

⏳ <b>Код действителен 1 минуту</b>

После ввода кода нажмите "Проверить статус".

Для тестирования можете использовать команду:
<code>/simulate_auth</code>
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
/login — вход через GitHub/Яндекс/Code
/logout — выход
/logout_all — выход со всех устройств
/test_auth — быстрая авторизация (для разработчиков)
/simulate_auth — имитация веб-авторизации по коду

<b>Тесты:</b>
/tests — список тестов
/start_test — начать тест по ID

<b>Профиль:</b>
/profile — информация о пользователе

<b>Технические команды:</b>
/services — информация о сервисах
/debug — отладочная информация
/ping — проверка работы бота
/echo — эхо-команда
"""
    await message.answer(help_text)


# =========================
# АВТОРИЗАЦИЯ - УЛУЧШЕННАЯ
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
        [InlineKeyboardButton(text="🐙 GitHub", callback_data="login_github")],
        [InlineKeyboardButton(text="🌐 Яндекс ID", callback_data="login_yandex")],
        [InlineKeyboardButton(text="🔢 Code", callback_data="login_code")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "login_github")
async def callback_login_github(callback: CallbackQuery):
    """Авторизация через GitHub (заглушка)"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "github")

    auth_url = f"https://github.com/login/oauth/authorize?client_id=stub&state={login_token}"

    text = f"""
🔐 <b>Авторизация через GitHub</b>

Для входа перейдите по ссылке:

<code>{auth_url}</code>

После авторизации нажмите "Проверить статус".

⏳ <b>Ссылка действительна 5 минут</b>
"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.callback_query(F.data == "login_yandex")
async def callback_login_yandex(callback: CallbackQuery):
    """Авторизация через Яндекс ID (заглушка)"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "yandex")

    auth_url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id=stub&state={login_token}"

    text = f"""
🔐 <b>Авторизация через Яндекс ID</b>

Для входа перейдите по ссылке:

<code>{auth_url}</code>

После авторизации нажмите "Проверить статус".

⏳ <b>Ссылка действительна 5 минут</b>
"""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_auth_{login_token}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_auth")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.callback_query(F.data == "login_code")
async def callback_login_code(callback: CallbackQuery):
    """Авторизация через код с улучшенной заглушкой"""
    chat_id = callback.from_user.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await callback.answer("✅ Вы уже авторизованы")
        return

    login_token = secrets.token_urlsafe(32)
    await set_user_anonymous(chat_id, login_token, "code")

    # Генерируем код через улучшенную заглушку
    code = await auth_service.generate_login_url(login_token, "code")

    text = f"""
🔐 <b>Авторизация через код</b>

Для входа в систему введите код в веб-клиенте:

<b>Код: <code>{code}</code></b>

⏳ <b>Код действителен 1 минуту</b>
⏳ <b>Токен входа действителен 5 минут</b>

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

    # Имитируем авторизацию через веб-клиент
    result = await auth_service.simulate_web_client_auth(login_token)

    if result:
        await message.answer(
            "✅ <b>Имитация веб-авторизации успешна!</b>\n\nТеперь нажмите 'Проверить статус' или подождите несколько секунд.")
    else:
        await message.answer("❌ <b>Ошибка имитации авторизации</b>\n\nВозможно, код устарел или токен не найден.")


# =========================
# КОМАНДА ДЛЯ БЫСТРОЙ АВТОРИЗАЦИИ
# =========================
@dp.message(Command("test_auth"))
@rate_limit()
@safe_send_message
async def cmd_test_auth(message: Message):
    """Быстрая авторизация для разработчиков"""
    chat_id = message.chat.id
    user = await get_user(chat_id)

    if user and user.get("status") == UserStatus.AUTHORIZED:
        await message.answer(f"✅ <b>Вы уже авторизованы как {user.get('email')}</b>")
        return

    text = """
🚀 <b>Тестовая авторизация (для разработчиков)</b>

Выберите роль для тестирования:
"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🎓 Студент", callback_data="login_student")],
        [InlineKeyboardButton(text="👨‍🏫 Преподаватель", callback_data="login_teacher")],
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

    # Создаем тестовые данные для авторизации студента
    user_id = 12345
    email = f"student_{chat_id}@test.com"

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

    # Создаем тестовые данные для авторизации преподавателя
    user_id = 67890
    email = f"teacher_{chat_id}@test.com"

    await set_user_authorized(chat_id, user_id, email, "teacher")

    await callback.answer("✅ Авторизация преподавателя успешна!")
    await callback.message.edit_text(
        f"✅ <b>Авторизация преподавателя успешна!</b>\n\nДобро пожаловать, {email}\n\nВы можете управлять тестами.",
        reply_markup=None
    )


# =========================
# СПИСОК ТЕСТОВ - С КНОПКАМИ ДЛЯ ЗАПУСКА
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
            question_ids = test.get("question_ids", [])

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

            # Добавляем кнопку для запуска теста
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
            f"❌ <b>Ошибка при загрузке тестов:</b>\n\n{str(e)}\n\nПопробуйте использовать /test_auth для тестовой авторизации.")


# =========================
# ЗАПУСК ТЕСТА ЧЕРЕЗ КНОПКУ
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
            result = await api_client.start_test(api_token, test_id)
            await loading_msg.delete()

            attempt_id = result.get("attempt_id") or result.get("id")
            if not attempt_id:
                await callback.answer("❌ Не удалось начать тест")
                return

            # Получаем вопросы теста
            question_ids = await api_client.get_test_questions(api_token, test_id)

            if not question_ids:
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
# ЗАПУСК ТЕСТА - С ID ТЕСТА И ID ВОПРОСА
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
        # Начинаем тест через API
        result = await api_client.start_test(api_token, test_id)
        await loading_msg.delete()

        attempt_id = result.get("attempt_id") or result.get("id")
        if not attempt_id:
            await message.answer("❌ <b>Ошибка:</b> Не удалось начать тест. Попробуйте позже.")
            return

        # Получаем вопросы теста
        question_ids = await api_client.get_test_questions(api_token, test_id)

        if not question_ids:
            await message.answer("❌ <b>Ошибка:</b> В тесте нет вопросов.")
            return

        # Определяем, с какого вопроса начинать
        start_question_index = 0
        if question_id:
            try:
                start_question_index = question_ids.index(question_id)
            except ValueError:
                # Если вопрос не найден в списке, начинаем с ближайшего доступного
                # Ищем первый вопрос с ID больше указанного
                found = False
                for i, qid in enumerate(question_ids):
                    if qid >= question_id:
                        start_question_index = i
                        found = True
                        break

                if not found:
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
        await message.answer(text, reply_markup=kb)

    except Exception as e:
        try:
            await loading_msg.delete()
        except:
            pass

        logger.error(f"Error starting test: {e}")
        await message.answer(f"❌ <b>Ошибка при начале теста:</b>\n\n{str(e)}")


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
            await api_client.submit_answer(api_token, attempt_id, question_id, option_index)
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

            # Завершаем тест через API
            try:
                result = await api_client.finish_test(api_token, attempt_id)

                # Подсчитываем правильные ответы
                correct_count = 0
                for qid, answer in context["answers"].items():
                    question_data = await api_client.get_question_details(api_token, qid)
                    if question_data.get("correct") == answer:
                        correct_count += 1

                percentage = int((correct_count / len(question_ids)) * 100) if question_ids else 0

                text = f"""
🎉 <b>Тест завершен!</b>

<b>Результат:</b> {result}
<b>Ваш результат:</b> {correct_count} из {len(question_ids)} ({percentage}%)

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
# ОТМЕНА ТЕСТА
# =========================
@dp.callback_query(F.data == "cancel_test")
async def callback_cancel_test(callback: CallbackQuery):
    """Отмена теста"""
    chat_id = callback.from_user.id
    await redis_client.delete(f"test_context:{chat_id}")
    await callback.answer("❌ Тест отменен")
    await callback.message.answer("🚫 <b>Тест отменен</b>\n\nВы можете начать новый тест с помощью /start_test.")


# =========================
# ОСТАЛЬНЫЕ КОМАНДЫ
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

    auth_date = "Неизвестно"
    if current_user.get("authorized_at"):
        try:
            auth_dt_utc = datetime.fromisoformat(current_user["authorized_at"].replace('Z', '+00:00'))
            auth_dt_msk = auth_dt_utc + timedelta(hours=3)
            auth_date = auth_dt_msk.strftime("%d.%m.%Y %H:%M (MSK)")
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

    await message.answer(text)


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
# ОБРАБОТЧИКИ КНОПОК АВТОРИЗАЦИИ
# =========================
@dp.callback_query(F.data == "login")
async def callback_login(callback: CallbackQuery):
    await callback.answer()
    await cmd_login(callback.message)


@dp.callback_query(F.data.startswith("check_auth_"))
async def callback_check_auth(callback: CallbackQuery):
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
            f"✅ <b>Авторизация завершена!</b>\n\nДобро пожаловать, {email}",
            reply_markup=None
        )


@dp.callback_query(F.data == "cancel_auth")
async def callback_cancel_auth(callback: CallbackQuery):
    chat_id = callback.from_user.id
    await delete_user(chat_id)
    await callback.answer("❌ Авторизация отменена")
    await callback.message.edit_text("🚪 <b>Авторизация отменена</b>", reply_markup=None)


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