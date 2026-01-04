import os
import logging
import asyncio
from datetime import datetime
from typing import Optional
import uuid
import redis
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
    WEB_CLIENT_URL = "http://localhost:3000"
    CORE_API_URL = "http://core-service:8082"
    AUTH_API_URL = "http://auth-service:8081"
    REDIS_URL = "redis://redis:6379/0"


# Глобальный пул соединений с Redis (оптимизировано для повторного использования)
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
            'start_time': datetime.now(),  # Local time по TZ контейнера
            'total_commands': 0,
            'active_users': set(),
        }

    def get_status(self) -> str:
        """Получить статус системы"""
        now = datetime.now()  # Local time
        lines = [
            "🖥️ <b>СТАТУС СИСТЕМЫ</b>",
            f"Время: {now.strftime('%H:%M:%S')}",
            f"Активна: {(now - self.stats['start_time']).seconds // 60} мин",
            "",
            "<b>Сервисы:</b>"
        ]

        for service, info in self.services.items():
            lines.append(f"• {service}: {info['status']} :{info['port']}")

        lines.extend([
            "",
            "<b>Статистика:</b>",
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
        lines = ["🔧 <b>СЕРВИСЫ СИСТЕМЫ</b>", ""]

        for service, info in self.services.items():
            lines.append(f"<b>{service.upper()}</b>")
            lines.append(f"Статус: {info['status']}")
            lines.append(f"Порт: <code>{info['port']}</code>")
            if 'url' in info:
                lines.append(f"URL: <code>{info['url']}</code>")
            lines.append("")

        return "\n".join(lines)

    def get_help(self) -> str:
        """Получить справку с списком доступных команд"""
        return """🤖 <b>ПОМОЩЬ И СПРАВКА</b>

🚀 <b>Основные команды:</b>
• /start - Начать работу с ботом
• /status - Проверить статус системы
• /services - Детали о сервисах
• /help - Эта справка с командами
• /login - Начать процесс авторизации
• /complete_login - Завершить авторизацию (или /completelogin)
• /tests - Просмотреть список тестов (требует авторизации)
• /start_test &lt;test_id&gt; - Запустить тест (или /starttest &lt;test_id&gt;)

🔧 <b>Техническая информация:</b>
• 📊 PostgreSQL: <code>localhost:5432</code>
• 🗄️ MongoDB: <code>localhost:27017</code>
• ⚡ Redis: <code>localhost:6379</code>

🛠️ <b>Функции в разработке:</b>
• Полное прохождение тестов с ответами
• Личный кабинет пользователя
• Уведомления о результатах

Если возникли вопросы, используйте /status для проверки системы!"""


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

📊 <b>Что уже работает:</b>
• Контейнеры Docker подняты
• Базы данных запущены  
• Веб-интерфейс доступен
• API сервисы готовы
• Базовая авторизация через веб

🔧 <b>Что будет добавлено:</b>
• Полное прохождение тестов
• Уведомления

<b>Список команд:</b>
/start - Начало работы
/status - Статус системы
/services - Информация о сервисах
/help - Справка
/login - Начать авторизацию
/complete_login - Завершить авторизацию
/tests - Список тестов
/start_test &lt;id&gt; - Начать тест

🌐 <b>Ссылки:</b>
• Веб-интерфейс: {Config.WEB_CLIENT_URL}
• API Core: {Config.CORE_API_URL}
• API Auth: {Config.AUTH_API_URL}"""

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🖥️ Статус", callback_data="status")],
            [InlineKeyboardButton(text="🔧 Сервисы", callback_data="services")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
            [InlineKeyboardButton(text="🔐 Авторизация", callback_data="login")],
        ])

        await message.reply(welcome_msg, parse_mode='HTML', reply_markup=keyboard)

    @dp.message(Command("status"))
    async def on_status(message: types.Message):
        monitor.stats['total_commands'] += 1
        await message.reply(monitor.get_status(), parse_mode='HTML')

    @dp.message(Command("services"))
    async def on_services(message: types.Message):
        monitor.stats['total_commands'] += 1
        await message.reply(monitor.get_services(), parse_mode='HTML')

    @dp.message(Command("help"))
    async def on_help(message: types.Message):
        monitor.stats['total_commands'] += 1
        await message.reply(monitor.get_help(), parse_mode='HTML')

    @dp.message(Command("login"))
    async def on_login(message: types.Message, state: FSMContext):
        monitor.stats['total_commands'] += 1
        redis_client = redis.Redis(connection_pool=redis_pool)
        code = uuid.uuid4().hex[:8].upper()
        user_id = str(message.from_user.id)
        redis_client.set(f"login:{code}", user_id, ex=600)
        msg = f"Для авторизации введите пароль в бек-клиент. Ваш код: {code}. После ввода кода в бек-клиенте используйте /complete_login здесь."
        await message.reply(msg, parse_mode='HTML')

    @dp.message(Command(commands=["complete_login", "completelogin"]))
    async def on_complete_login(message: types.Message, state: FSMContext):
        monitor.stats['total_commands'] += 1
        redis_client = redis.Redis(connection_pool=redis_pool)
        keys = redis_client.keys("auth_token:*")
        found = False
        for key in keys:
            user_id = redis_client.get(key)
            if user_id and int(user_id) == message.from_user.id:
                token = key.split(":", 1)[1]
                await message.reply(f"✅ Авторизация завершена! Токен: <code>{token}</code>", parse_mode='HTML')
                await state.update_data(headers={"Authorization": f"Bearer {token}"})
                found = True
                break
        if not found:
            await message.reply("Сессия авторизации не найдена. Начните заново с /login", parse_mode='HTML')

    @dp.message(Command("tests"))
    async def on_tests(message: types.Message, state: FSMContext):
        monitor.stats['total_commands'] += 1
        data = await state.get_data()
        headers = data.get('headers')
        if not headers:
            await message.reply("Сначала авторизуйтесь через /login", parse_mode='HTML')
            return
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{Config.CORE_API_URL}/tests", headers=headers, timeout=5) as response:
                    if response.status != 200:
                        await message.reply(f"Ошибка: {response.status}", parse_mode='HTML')
                        return
                    tests = await response.json()
            except Exception as e:
                logger.error(f"API error: {e}")
                await message.reply("Ошибка соединения с Core API. Попробуйте позже.", parse_mode='HTML')
                return
        if not tests:
            await message.reply("Нет доступных тестов.", parse_mode='HTML')
            return
        msg = "📋 <b>Доступные тесты:</b>\n"
        for test in tests:
            msg += f"• ID: {test['id']} - {test['title']}\n"
        await message.reply(msg, parse_mode='HTML')

    @dp.message(Command(commands=["start_test", "starttest"]))
    async def on_start_test(message: types.Message, state: FSMContext):
        monitor.stats['total_commands'] += 1
        data = await state.get_data()
        headers = data.get('headers')
        if not headers:
            await message.reply("Сначала авторизуйтесь через /login", parse_mode='HTML')
            return
        args = message.text.split()
        if len(args) < 2:
            await message.reply("Использование: /start_test &lt;test_id&gt;", parse_mode='HTML')
            return
        test_id = args[1]
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{Config.CORE_API_URL}/attempts", json={"test_id": test_id}, headers=headers, timeout=5) as response:
                    if response.status != 201:
                        await message.reply(f"Ошибка начала теста: {response.status}", parse_mode='HTML')
                        return
                    attempt = await response.json()
            except Exception as e:
                logger.error(f"API error: {e}")
                await message.reply("Ошибка соединения с Core API. Попробуйте позже.", parse_mode='HTML')
                return
        await state.set_state(TestStates.answering)
        await state.set_data({
            'attempt_id': attempt['id'],
            'question_ids': attempt['question_ids'],
            'current_index': 0,
            'headers': headers
        })
        await send_next_question(message, state)

    async def send_next_question(message_or_callback, state: FSMContext):
        data = await state.get_data()
        index = data['current_index']
        question_id = data['question_ids'][index]
        headers = data['headers']
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{Config.CORE_API_URL}/questions/{question_id}", headers=headers,
                                       timeout=5) as response:
                    if response.status != 200:
                        await message_or_callback.reply(f"Ошибка при получении вопроса: {response.status}",
                                                        parse_mode='HTML')
                        await state.clear()
                        return
                    q = await response.json()
            except Exception as e:
                logger.error(f"API error: {e}")
                await message_or_callback.reply("Ошибка соединения с Core API. Попробуйте позже.",
                                                parse_mode='HTML')
                await state.clear()
                return

        msg = f"Вопрос {index + 1}/{len(data['question_ids'])}: {q['question_text']}"
        inline_kb = [
            [InlineKeyboardButton(text=option, callback_data=f"ans:{i}:{question_id}") for i, option in
             enumerate(q['options'])]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=inline_kb)
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.reply(msg, reply_markup=keyboard, parse_mode='HTML')
        else:
            await message_or_callback.message.edit_text(msg, reply_markup=keyboard, parse_mode='HTML')

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
                        await callback.message.reply(f"Ошибка сохранения ответа: {response.status}",
                                                     parse_mode='HTML')
                        await state.clear()
                        return
            except Exception as e:
                logger.error(f"API error: {e}")
                await callback.message.reply("Ошибка соединения с Core API. Попробуйте позже.",
                                             parse_mode='HTML')
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
                            await callback.message.reply(f"Ошибка завершения теста: {response.status}",
                                                         parse_mode='HTML')
                        else:
                            res = await response.json()
                            score = res.get('score', 'N/A')
                            await callback.message.reply(f"Тест завершен! Результат: {score}", parse_mode='HTML')
                except Exception as e:
                    logger.error(f"API error: {e}")
                    await callback.message.reply("Ошибка соединения с Core API. Попробуйте позже.",
                                                 parse_mode='HTML')
            await state.clear()
        else:
            await state.update_data(current_index=new_index)
            await send_next_question(callback, state)
        await callback.answer()

    @dp.callback_query()
    async def on_callback(callback: types.CallbackQuery):
        if callback.data == 'status':
            await callback.message.edit_text(monitor.get_status(), parse_mode='HTML')
        elif callback.data == 'services':
            await callback.message.edit_text(monitor.get_services(), parse_mode='HTML')
        elif callback.data == 'help':
            await callback.message.edit_text(monitor.get_help(), parse_mode='HTML')
        elif callback.data == 'login':
            chat_id = callback.message.chat.id
            user_id = callback.from_user.id
            state = FSMContext(storage=dp.storage, chat=chat_id, user=user_id)
            await on_login(callback.message, state)
        await callback.answer()

    @dp.message()
    async def on_unknown(message: types.Message):
        if message.text and message.text.startswith('/'):
            await message.reply("❓ Неизвестная команда.\nИспользуйте /help для списка доступных команд.",
                                parse_mode='HTML')

    logger.info("🤖 Бот запущен. Нажмите Ctrl+C для остановки")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())а