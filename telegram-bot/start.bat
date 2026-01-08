@echo off
echo ========================================
echo ЗАПУСК TELEGRAM БОТА
echo ========================================

echo 1. Остановка старых контейнеров...
docker-compose -f docker-compose.fixed.yml down

echo 2. Создание файла .env.docker...
echo TELEGRAM_BOT_TOKEN=8502404802:AAFEHiSEHaZsJuSClII20ul1jJnyMeaodg4 > .env.docker
echo REDIS_URL=redis://telegram-bot-redis:6379/0 >> .env.docker
echo API_BASE_URL=http://localhost:8082 >> .env.docker
echo AUTH_SERVICE_URL=http://localhost:8081 >> .env.docker
echo JWT_SECRET=development_secret_change_this_in_production >> .env.docker
echo DEFAULT_COURSE_ID=1 >> .env.docker
echo HTTP_PORT=8083 >> .env.docker

echo 3. Построение Docker образа...
docker-compose -f docker-compose.fixed.yml build --no-cache

echo 4. Запуск контейнеров...
docker-compose -f docker-compose.fixed.yml up -d

echo 5. Ожидание запуска (3 секунды)...
timeout /t 3 /nobreak > nul

echo 6. Проверка статуса...
docker-compose -f docker-compose.fixed.yml ps

echo 7. Логи бота...
docker-compose -f docker-compose.fixed.yml logs --tail=10 telegram-bot

echo ========================================
echo ✅ Бот запущен!
echo ========================================
echo Проверьте бота: http://localhost:8083/health
pause