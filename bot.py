import os
import logging
import asyncio
from datetime import datetime
from typing import Optional
import uuid
import redis.asyncio as redis
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv

load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# Глобальные настройки
class Config:
    """Конфигурация бота"""
    TELEGRAM_TOKEN: Optional[str] = None
    WEB_CLIENT_URL = "https://localhost:3000"
    CORE_API_URL = "http://core-service:8082"
    AUTH_API_URL = "http://auth-service:8081"
    REDIS_URL = "redis://redis:6379/0"


# Global Redis connection pool
redis_pool = redis.ConnectionPool.from_url(Config.REDIS_URL, decode_responses=True)


class SystemMonitor:
    """Мониторинг состояния системы"""

    def __init__(self):
        self.services = {
            'core-service': {'status': '🟢 Онлайн', 'port': 8082, 'url': Config.CORE_API_URL},
            'auth-service': {'status': '🟢 Онлайн', 'port': 8081, 'url': Config.AUTH_API_URL},
            'web-client': {'status': '🟢 Онлайн', 'port': 3000, 'url': Config.WEB_CLIENT_URL},
            'postgres': {'status': '🟢 Онлайн', 'port': 5432},
            'mongodb': {'status': '🟢 Онлайн', 'port': 27017},
            'redis': {'status': '🟢 Онлайн', 'port': 6379, 'url': Config.REDIS_URL},
        }

        self.stats = {
            'start_time': datetime.now(),
            'total_commands': 0,
            'active_users': set(),
        }

    def get_status(self) -> str:
        """Получить статус системы"""
        lines = [
            "🖥️ *СТАТУС СИСТЕМЫ*",
            f"Время: {datetime.now().strftime('%H:%M:%S')}",
            f"Активна: {(datetime.now() - self.stats['start_time']).seconds // 60} мин",
            "",
            "*Сервисы:*"
        ]

        for service, info in self.services.items():
            lines.append(f"• {service}: {info['status']} :{info['port']}")

        lines.extend([
            "",
            "*Статистика:*",
            f"Команд выполнено: {self.stats['total_commands']}",
            f"Активных пользователей: {len(self.stats['active_users'])}",
            "",
            f"🌐 Веб-интерфейс: {Config.WEB_CLIENT_URL}",
            f"🔧 API Core: {Config.CORE_API_URL}",
            f"🔐 API Auth: {Config.AUTH_API_URL}",
        ])

        return "\n".join(lines)

    def get_services(self) -> str:
        """Получить детальную информацию о сервисах"""
        lines = ["🔧 *СЕРВИСЫ СИСТЕМЫ*", ""]

        for service, info in self.services.items():
            lines.append(f"*{service.upper()}*")
            lines.append(f"Статус: {info['status']}")
            lines.append(f"Порт: {info['port']}")
            if 'url' in info:
                lines.append(f"URL: {info['url']}")
            lines.append("")

        return "\n".join(lines)

    def get_help(self) -> str:
        """Получить справку"""
        return """🆘 *ПОМОЩЬ ПО КОМАНДАМ*

*Основные команды:*
/start - Начало работы
/status - Статус системы
/services - Информация о сервисах
/help - Эта справка
/login - Авторизация
/completelogin - Завершить авторизацию после веб-клиента
/tests - Список доступных тестов (после авторизации)
/starttest <test_id> - Начать тест (после авторизации)

*Технические данные:*
📊 PostgreSQL: localhost:5432
🗄️ MongoDB: localhost:27017
⚡ Redis: localhost:6379

🚧 *В РАЗРАБОТКЕ:* 
• Полное прохождение тестов
• Личный кабинет
"""


class TestStates(StatesGroup):
    answering = State()


async def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("❌ Токен бота не установлен!")
        return

    Config.TELEGRAM_TOKEN = token

    bot = Bot(token=token)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    monitor = SystemMonitor()

    @dp.message(Command("start"))
    async def on_start(message: types.Message):
        monitor.stats['total_commands'] += 1
        monitor.stats['active_users'].add(message.from_user.id)

        welcome_msg = f"""👋 Привет, {message.from_user.first_name}!

🤖 Я - бот системы тестирования.
Система находится в стадии активной разработки.

📊 *Что уже работает:*
• Контейнеры Docker подняты
• Базы данных запущены  
• Веб-интерфейс доступен
• API сервисы готовы
• Базовая авторизация через веб

🔧 *Что будет добавлено:*
• Полное прохождение тестов
• Уведомления

*Основные команды:*
/start - Начало работы
/status - Статус системы
/services - Информация о сервисах
/help - Эта справка
/login - Начать авторизацию
/completelogin - Завершить авторизацию
/tests - Список тестов
/starttest <id> - Начать тест

🌐 *Ссылки:*
• Веб-интерфейс: {Config.WEB_CLIENT_URL}
• API Core: {Config.CORE_API_URL}
• API Auth: {Config.AUTH_API_URL}"""

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='📊 Статус', callback_data='status')],
            [InlineKeyboardButton(text='🔧 Сервисы', callback_data='services')],
            [InlineKeyboardButton(text='🆘 Помощь', callback_data='help')],
            [InlineKeyboardButton(text='🔐 Авторизация', callback_data='login')],
        ])

        await message.reply(welcome_msg, parse_mode='Markdown', reply_markup=keyboard)

    @dp.message(Command("status"))
    async def on_status(message: types.Message):
        monitor.stats['total_commands'] += 1
        await message.reply(monitor.get_status(), parse_mode='Markdown')

    @dp.message(Command("services"))
    async def on_services(message: types.Message):
        monitor.stats['total_commands'] += 1
        await message.reply(monitor.get_services(), parse_mode='Markdown')

    @dp.message(Command("help"))
    async def on_help(message: types.Message):
        monitor.stats['total_commands'] += 1
        await message.reply(monitor.get_help(), parse_mode='Markdown')

    @dp.message(Command("login"))
    async def on_login(message: types.Message):
        monitor.stats['total_commands'] += 1
        state_uuid = str(uuid.uuid4())
        r = redis.Redis(connection_pool=redis_pool)
        try:
            await r.set(f"auth_state:{state_uuid}", str(message.from_user.id), ex=3600)
        except Exception as e:
            logger.error(f"Redis error: {e}")
            await message.reply("Ошибка соединения с Redis. Попробуйте позже.")
            return
        finally:
            await r.aclose()

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='GitHub', url=f"{Config.WEB_CLIENT_URL}/auth/github?state={state_uuid}")],
            [InlineKeyboardButton(text='Yandex ID', url=f"{Config.WEB_CLIENT_URL}/auth/yandex?state={state_uuid}")],
            [InlineKeyboardButton(text='Code', url=f"{Config.WEB_CLIENT_URL}/auth/code?state={state_uuid}")]
        ])

        msg = "Пожалуйста, выберите метод авторизации:"
        await message.reply(msg, reply_markup=keyboard)

    @dp.message(Command("completelogin"))
    async def on_completelogin(message: types.Message):
        monitor.stats['total_commands'] += 1
        user_id = message.from_user.id
        state = None
        r = redis.Redis(connection_pool=redis_pool)
        try:
            async for key in r.scan_iter("auth_state:*"):
                if await r.get(key) == str(user_id):
                    state = key.split(':')[1]
                    break
        except Exception as e:
            logger.error(f"Redis error: {e}")
            await message.reply("Ошибка соединения с Redis. Попробуйте позже.")
            return
        finally:
            await r.aclose()

        if not state:
            await message.reply("Не найдена активная сессия авторизации. Начните заново с /login.")
            return

        r = redis.Redis(connection_pool=redis_pool)
        jwt_key = f"auth_jwt:{state}"
        try:
            jwt = await r.get(jwt_key)
            if not jwt:
                await message.reply("Авторизация еще не завершена в веб-клиенте. Попробуйте позже или начните заново.")
                return
            await r.set(f"user_jwt:{user_id}", jwt, ex=86400)
            await r.delete(f"auth_state:{state}")
            await r.delete(jwt_key)
        except Exception as e:
            logger.error(f"Redis error: {e}")
            await message.reply("Ошибка сохранения токена. Попробуйте позже.")
            return
        finally:
            await r.aclose()

        await message.reply(
            "**Авторизация завершена успешно!** 🎉\nТеперь вы можете использовать защищенные команды, такие как /tests и /starttest.",
            parse_mode='Markdown')

    @dp.message(Command("tests"))
    async def on_tests(message: types.Message):
        monitor.stats['total_commands'] += 1
        user_id = message.from_user.id
        r = redis.Redis(connection_pool=redis_pool)
        jwt = await r.get(f"user_jwt:{user_id}")
        await r.aclose()
        if not jwt:
            await message.reply("Сначала авторизуйтесь с помощью /login и /completelogin.")
            return

        headers = {"Authorization": f"Bearer {jwt}"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{Config.CORE_API_URL}/tests", headers=headers, timeout=5) as response:
                    if response.status != 200:
                        await message.reply(f"Ошибка при получении тестов: {response.status}")
                        return
                    tests_data = await response.json()
                    msg = "📚 **Доступные тесты:**\n\n"
                    tests = tests_data.get('tests', [])
                    if not tests:
                        msg += "Нет доступных тестов. 😔"
                    else:
                        for test in tests:
                            msg += f"🔹 **{test.get('test_name', 'Без названия')}** (ID: {test.get('id')})\n"
            except Exception as e:
                logger.error(f"API error: {e}")
                msg = "Ошибка соединения с Core API. Попробуйте позже."

        await message.reply(msg, parse_mode='Markdown')

    @dp.message(Command("starttest"))
    async def on_starttest(message: types.Message, state: FSMContext):
        monitor.stats['total_commands'] += 1
        args = message.text.split()
        if len(args) < 2:
            await message.reply("**Использование:** /starttest <test_id> 🚀")
            return
        test_id = args[1]
        user_id = message.from_user.id
        r = redis.Redis(connection_pool=redis_pool)
        jwt = await r.get(f"user_jwt:{user_id}")
        await r.aclose()
        if not jwt:
            await message.reply("Сначала авторизуйтесь с помощью /login и /completelogin.")
            return

        headers = {"Authorization": f"Bearer {jwt}"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{Config.CORE_API_URL}/attempts", json={"test_id": test_id}, headers=headers,
                                        timeout=5) as response:
                    if response.status != 201:
                        await message.reply(f"Ошибка при создании попытки: {response.status}")
                        return
                    data = await response.json()
                    attempt_id = data.get('attempt_id')
                    if not attempt_id:
                        await message.reply("Ошибка: не получен ID попытки.")
                        return
            except Exception as e:
                logger.error(f"API error: {e}")
                await message.reply("Ошибка соединения с Core API. Попробуйте позже.")
                return

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{Config.CORE_API_URL}/tests/{test_id}/questions", headers=headers,
                                       timeout=5) as response:
                    if response.status != 200:
                        await message.reply(f"Ошибка при получении вопросов: {response.status}")
                        return
                    questions_data = await response.json()
                    questions = questions_data.get('questions', [])
                    if not questions:
                        await message.reply("В тесте нет вопросов.")
                        return
                    # Assume questions is list of {'question_id': id, 'order_index': n}
                    questions.sort(key=lambda x: x['order_index'])
                    question_ids = [q['question_id'] for q in questions]
            except Exception as e:
                logger.error(f"API error: {e}")
                await message.reply("Ошибка соединения с Core API. Попробуйте позже.")
                return

        await state.set_state(TestStates.answering)
        await state.set_data({
            'attempt_id': attempt_id,
            'question_ids': question_ids,
            'current_index': 0,
            'headers': headers
        })
        await send_next_question(message, state)

    async def send_next_question(message_or_callback: types.Message | types.CallbackQuery, state: FSMContext):
        data = await state.get_data()
        index = data['current_index']
        question_id = data['question_ids'][index]
        headers = data['headers']
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{Config.CORE_API_URL}/questions/{question_id}", headers=headers,
                                       timeout=5) as response:
                    if response.status != 200:
                        await message_or_callback.reply(f"Ошибка при получении вопроса: {response.status}")
                        await state.clear()
                        return
                    q = await response.json()
                    # Assume q = {'question_name': str, 'question_text': str, 'options': list[str]}
            except Exception as e:
                logger.error(f"API error: {e}")
                await message_or_callback.reply("Ошибка соединения с Core API. Попробуйте позже.")
                await state.clear()
                return

        msg = f"Вопрос {index + 1}/{len(data['question_ids'])}: {q['question_text']}"
        inline_kb = [
            [InlineKeyboardButton(text=option, callback_data=f"ans:{i}:{question_id}") for i, option in
             enumerate(q['options'])]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=inline_kb)
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.reply(msg, reply_markup=keyboard)
        else:
            await message_or_callback.message.edit_text(msg, reply_markup=keyboard)

    @dp.callback_query(lambda c: c.data.startswith('ans:'), TestStates.answering)
    async def on_answer(callback: types.CallbackQuery, state: FSMContext):
        parts = callback.data.split(':')
        ans_index = int(parts[1])
        question_id = int(parts[2])
        data = await state.get_data()
        if data['question_ids'][data['current_index']] != question_id:
            await callback.answer("Неверный вопрос.")
            return
        attempt_id = data['attempt_id']
        headers = data['headers']
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                        f"{Config.CORE_API_URL}/attempts/{attempt_id}/answers",
                        json={"question_id": question_id, "selected_answer": ans_index},
                        headers=headers,
                        timeout=5
                ) as response:
                    if response.status != 200:
                        await callback.message.reply(f"Ошибка сохранения ответа: {response.status}")
                        await state.clear()
                        return
            except Exception as e:
                logger.error(f"API error: {e}")
                await callback.message.reply("Ошибка соединения с Core API. Попробуйте позже.")
                await state.clear()
                return

        new_index = data['current_index'] + 1
        if new_index >= len(data['question_ids']):
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(
                            f"{Config.CORE_API_URL}/attempts/{attempt_id}/complete",
                            headers=headers,
                            timeout=5
                    ) as response:
                        if response.status != 200:
                            await callback.message.reply(f"Ошибка завершения теста: {response.status}")
                        else:
                            res = await response.json()
                            score = res.get('score', 'N/A')
                            await callback.message.reply(f"**Тест завершен!** 🎉\nРезультат: {score}")
                except Exception as e:
                    logger.error(f"API error: {e}")
                    await callback.message.reply("Ошибка соединения с Core API. Попробуйте позже.")
            await state.clear()
        else:
            await state.update_data(current_index=new_index)
            await send_next_question(callback, state)
        await callback.answer()

    @dp.callback_query()
    async def on_callback(callback: types.CallbackQuery):
        if callback.data == 'status':
            await callback.message.edit_text(monitor.get_status(), parse_mode='Markdown')
        elif callback.data == 'services':
            await callback.message.edit_text(monitor.get_services(), parse_mode='Markdown')
        elif callback.data == 'help':
            await callback.message.edit_text(monitor.get_help(), parse_mode='Markdown')
        elif callback.data == 'login':
            await on_login(callback.message)
        await callback.answer()

    @dp.message()
    async def on_unknown(message: types.Message):
        if message.text and message.text.startswith('/'):
            await message.reply("❓ Неизвестная команда.\nИспользуйте /help для списка доступных команд.",
                                parse_mode='Markdown')

    logger.info("🤖 Бот запущен. Нажмите Ctrl+C для остановки")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())