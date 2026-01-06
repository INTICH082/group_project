import os
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import aiohttp
import redis.asyncio as redis
from pymongo import MongoClient  # Для Mongo

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram import Router, F
from aiogram.utils.markdown import hbold, hcode
from dotenv import load_dotenv
from aiogram_i18n import create_middleware, set_default_locale  # Правильный импорт для aiogram-i18n
from aiogram_i18n.types import Locale

load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные настройки
BOT_TOKEN = os.getenv('BOT_TOKEN')
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
AUTH_SERVICE_URL = os.getenv('AUTH_SERVICE_URL', 'http://auth-service:8081')
WEB_CLIENT_URL = os.getenv('WEB_CLIENT_URL', 'http://localhost:3000')
POSTGRES_URL = os.getenv('POSTGRES_URL', 'postgres://user:pass@postgres:5432/db')
MONGO_URL = os.getenv('MONGO_URL', 'mongodb://mongo:27017/db')  # Обновлено на mongodb://

if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN is not set')

bot = Bot(token=BOT_TOKEN, parse_mode='HTML')
dp = Dispatcher()

# Redis client
r = redis.from_url(REDIS_URL, decode_responses=True)

# Mongo client (async не нужен, используем sync для простоты, но в background task)
mongo_client = MongoClient(MONGO_URL)
mongo_db = mongo_client['db']  # База данных
events_collection = mongo_db['events']  # Коллекция для events/notifications

# FSM states
class AuthStates(StatesGroup):
    waiting_code = State()

class TestStates(StatesGroup):
    answering = State()

# Rate limiting middleware
from aiogram.dispatcher.middlewares import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: int = 1, period: int = 1):  # 1 команда в секунду
        self.rate_limit = rate_limit
        self.period = period
        self.user_timestamps = {}

    async def __call__(
        self,
        handler: Callable[[types.Message, Dict[str, Any]], Awaitable[Any]],
        event: types.Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        now = time.time()
        timestamps = self.user_timestamps.get(user_id, [])
        timestamps = [ts for ts in timestamps if now - ts < self.period]
        if len(timestamps) >= self.rate_limit:
            await event.reply("🚫 Слишком много запросов. Подождите секунду.")
            return
        timestamps.append(now)
        self.user_timestamps[user_id] = timestamps
        return await handler(event, data)

dp.message.middleware(ThrottlingMiddleware())

# i18n setup (для multi-lang ru/en)
i18n_middleware = create_middleware(domain='messages', locales=['ru', 'en'], default_locale='ru')
dp.message.middleware(i18n_middleware)

# System start time (MSK TZ)
START_TIME = datetime.now(timezone(timedelta(hours=3)))

# Mock tests
TESTS = {
    "1": {"name": "API Test", "questions": [{"id": 1, "text": "Question 1?", "options": ["A", "B"]}]},
    "2": {"name": "Load Test", "questions": [{"id": 2, "text": "Question 2?", "options": ["C", "D"]}]},
    "3": {"name": "UI Test", "questions": [{"id": 3, "text": "Question 3?", "options": ["E", "F"]}]},
}

# Background task для cyclic notifications (every 30 sec check Redis for ANONYMOUS, auth check, send updates)
async def cyclic_notification_task():
    while True:
        try:
            # Scan Redis for ANONYMOUS users
            async for key in r.scan_iter('user:*:status'):
                status = await r.get(key)
                if status == 'ANONYMOUS':
                    user_id = int(key.split(':')[1])
                    # Check auth via API (mock)
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{AUTH_SERVICE_URL}/check/{user_id}") as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if data.get('authorized'):
                                    await r.set(key, 'AUTHORIZED')
                                    await bot.send_message(user_id, "✅ Вы авторизованы!")
                                    # Save event to Mongo
                                    events_collection.insert_one({'user_id': user_id, 'event': 'authorized', 'timestamp': datetime.now()})

            # Poll Mongo for events (e.g., new notifications)
            for event in events_collection.find({'processed': {'$ne': True}}):
                user_id = event['user_id']
                await bot.send_message(user_id, f"Уведомление: {event['event']}")
                events_collection.update_one({'_id': event['_id']}, {'$set': {'processed': True}})

        except Exception as e:
            logger.error(f"Cyclic task error: {e}")
        await asyncio.sleep(30)  # Every 30 sec

# Start handler
@dp.message(Command('start'))
async def on_start(message: types.Message, state: FSMContext):
    text = """👋 Привет, {name}!

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

*Список команд:*
/start - Начало работы
/status - Статус системы
/services - Информация о сервисах
/help - Справка
/login - Начать авторизацию
/complete_login - Завершить авторизацию
/tests - Список тестов
/start_test <id> - Начать тест

🌐 *Ссылки:*
• Веб-интерфейс: {web_url}
• API Core: {core_url}
• API Auth: {auth_url}""".format(
        name=message.from_user.first_name,
        web_url=WEB_CLIENT_URL,
        core_url=AUTH_SERVICE_URL,  # Исправил на существующий, так как CORE_API_URL не определен
        auth_url=AUTH_SERVICE_URL
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text='📊 Статус', callback_data='status')
    keyboard.button(text='🔧 Сервисы', callback_data='services')
    keyboard.button(text='🆘 Помощь', callback_data='help')
    keyboard.button(text='🔐 Авторизация', callback_data='login')
    keyboard.adjust(2)

    await message.reply(text, reply_markup=keyboard.as_markup())

# Status handler
@dp.message(Command('status'))
async def on_status(message: types.Message):
    now = datetime.now(timezone(timedelta(hours=3)))
    uptime = (now - START_TIME).seconds // 60
    text = """🖥️ *СТАТУС СИСТЕМЫ*
Время: {time}
Активна: {uptime} мин

*Сервисы:*
• core-service: 🟢 Онлайн :8082
• auth-service: 🟢 Онлайн :8081
• web-client: 🟢 Онлайн :3000
• postgres: 🟢 Онлайн :5432
• mongodb: 🟢 Онлайн :27017
• redis: 🟢 Онлайн :6379

*Статистика:*
Команд выполнено: {commands}
Активных пользователей: {users}

🌐 Веб-интерфейс: {web_url}
🔧 API Core: {core_url}
🔐 API Auth: {auth_url}""".format(
        time=now.strftime('%H:%M:%S'),
        uptime=uptime,
        commands=0,  # Mock, add counter if needed
        users=0,  # Mock
        web_url=WEB_CLIENT_URL,
        core_url=AUTH_SERVICE_URL,  # Исправил
        auth_url=AUTH_SERVICE_URL
    )
    await message.reply(text)

# Services handler
@dp.message(Command('services'))
async def on_services(message: types.Message):
    text = """🔧 *СЕРВИСЫ СИСТЕМЫ*

*CORE-SERVICE*
Статус: 🟢 Онлайн
Порт: `8082`
URL: `{core_url}`

*AUTH-SERVICE*
Статус: 🟢 Онлайн
Порт: `8081`
URL: `{auth_url}`

*WEB-CLIENT*
Статус: 🟢 Онлайн
Порт: `3000`
URL: `{web_url}`

*POSTGRES*
Статус: 🟢 Онлайн
Порт: `5432`

*MONGODB*
Статус: 🟢 Онлайн
Порт: `27017`

*REDIS*
Статус: 🟢 Онлайн
Порт: `6379`
URL: `{redis_url}`""".format(
        core_url=AUTH_SERVICE_URL,  # Исправил
        auth_url=AUTH_SERVICE_URL,
        web_url=WEB_CLIENT_URL,
        redis_url=REDIS_URL
    )
    await message.reply(text)

# Help handler
@dp.message(Command('help'))
async def on_help(message: types.Message):
    text = """🆘 *ПОМОЩЬ ПО КОМАНДАМ*

*Основные команды:*
/start - Начало работы
/status - Статус системы
/services - Информация о сервисах
/help - Эта справка
/login - Авторизация
/complete_login - Завершить авторизацию после веб-клиента
/tests - Список доступных тестов (после авторизации)
 /start_test <test_id> - Начать тест (после авторизации)

*Технические данные:*
📊 PostgreSQL: `localhost:5432`
🗄️ MongoDB: `localhost:27017`
⚡ Redis: `localhost:6379`

🚧 *В РАЗРАБОТКЕ:* 
• Полное прохождение тестов
• Личный кабинет"""
    await message.reply(text)

# Login handler
@dp.message(Command('login'))
async def on_login(message: types.Message, state: FSMContext):
    code = uuid.uuid4().hex[:8].upper()
    user_id = message.from_user.id
    await r.setex(f'auth_code:{code}', 300, user_id)  # 5 мин
    text = "🔐 Для авторизации перейдите в веб-клиент: {url}/login\nВаш код: {code}\nПосле ввода кода в веб-клиенте используйте /complete_login <code> здесь.".format(
        url=WEB_CLIENT_URL,
        code=hcode(code)
    )
    await message.reply(text)
    await state.set_state(AuthStates.waiting_code)

# Complete login
@dp.message(Command('complete_login', 'completelogin'))
async def on_complete_login(message: types.Message, state: FSMContext):
    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Используйте: /complete_login <code>")
    code = args[1]
    user_id = message.from_user.id
    stored_id = await r.get(f'auth_code:{code}')
    if not stored_id or int(stored_id) != user_id:
        return await message.reply("🚫 Вы не авторизованы. Начните с /login.")
    # Mock auth check
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{AUTH_SERVICE_URL}/complete/{code}") as resp:
            if resp.status == 200:
                token = (await resp.json()).get('token')
                await state.update_data(token=token, status='AUTHORIZED')
                await r.delete(f'auth_code:{code}')
                await message.reply("✅ Авторизация завершена! Теперь доступны тесты.")
            else:
                await message.reply("Ошибка авторизации. Попробуйте позже.")
    await state.clear()

# Tests list with buttons
@dp.message(Command('tests'))
async def on_tests(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if data.get('status') != 'AUTHORIZED':
        return await message.reply("🚫 Вы не авторизованы. Используйте /login.")
    text = "📝 Доступные тесты:\n"
    keyboard = InlineKeyboardBuilder()
    for test_id, test in TESTS.items():
        text += f"• {test_id}: {test['name']}\n"
        keyboard.button(text=test['name'], callback_data=f"start_test:{test_id}")
    keyboard.adjust(1)
    await message.reply(text, reply_markup=keyboard.as_markup())

# Start test (from command or button)
@dp.message(Command('start_test', 'starttest'))
@dp.callback_query(F.data.startswith('start_test:'))
async def on_start_test(query: types.Message | CallbackQuery, state: FSMContext):
    if isinstance(query, CallbackQuery):
        test_id = query.data.split(':')[1]
        await query.answer()
        message = query.message
    else:
        args = query.text.split()
        if len(args) < 2:
            return await query.reply("Используйте: /start_test <test_id>")
        test_id = args[1]
        message = query

    data = await state.get_data()
    if data.get('status') != 'AUTHORIZED':
        return await message.reply("🚫 Вы не авторизованы. Используйте /login.")

    test = TESTS.get(test_id)
    if not test:
        return await message.reply("Тест не найден.")

    if not test['questions']:
        return await message.reply("В тесте нет вопросов.")

    # Mock attempt creation
    attempt_id = uuid.uuid4().hex
    question_ids = [q['id'] for q in test['questions']]

    await state.set_state(TestStates.answering)
    await state.update_data(attempt_id=attempt_id, question_ids=question_ids, current_index=0, test_id=test_id)

    await send_next_question(message, state)

async def send_next_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    index = data['current_index']
    q_id = data['question_ids'][index]
    q = next(q for q in TESTS[data['test_id']]['questions'] if q['id'] == q_id)  # Mock
    text = f"Вопрос {index + 1}/{len(data['question_ids'])}: {q['text']}"
    keyboard = InlineKeyboardBuilder()
    for i, opt in enumerate(q['options']):
        keyboard.button(text=opt, callback_data=f"ans:{i}:{q_id}")
    keyboard.adjust(1)
    await message.reply(text, reply_markup=keyboard.as_markup())

# Answer callback
@dp.callback_query(F.data.startswith('ans:'), TestStates.answering)
async def on_answer(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(':')
    ans_index = int(parts[1])
    q_id = int(parts[2])
    data = await state.get_data()
    if data['question_ids'][data['current_index']] != q_id:
        return await callback.answer("Неверный вопрос.")
    # Mock save save
    new_index = data['current_index'] + 1
    if new_index >= len(data['question_ids']):
        # Complete test
        await callback.message.reply("Тест завершен! Результат: N/A")
        await state.clear()
    else:
        await state.update_data(current_index=new_index)
        await send_next_question(callback.message, state)
    await callback.answer()

# Callback handler
@dp.callback_query()
async def on_callback(callback: CallbackQuery):
    if callback.data == 'status':
        await on_status(callback.message)
        await callback.message.edit_text(await on_status(callback.message))  # Wait for text
    elif callback.data == 'services':
        await callback.message.edit_text(await on_services(callback.message))
    elif callback.data == 'help':
        await callback.message.edit_text(await on_help(callback.message))
    elif callback.data == 'login':
        await on_login(callback.message, FSMContext(callback.message))
    await callback.answer()

# Error handling
@dp.errors()
async def on_error(update: types.Update, exception: Exception):
    if isinstance(exception, (aiohttp.ClientError, redis.RedisError)):
        logger.error(f"Error: {exception}")
        if update.message:
            await update.message.reply("Ошибка, попробуйте позже.")
    return True  # Skip update

# Unknown
@dp.message()
async def on_unknown(message: types.Message):
    if message.text.startswith('/'):
        await message.reply("❓ Неизвестная команда.\nИспользуйте /help для списка доступных команд.")

async def main():
    # Start cyclic task
    asyncio.create_task(cyclic_notification_task())
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    asyncio.run(main())