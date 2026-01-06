#!/bin/bash

echo "🚀 Запуск модуля авторизации..."
echo "Порт: 8081"
echo "GitHub OAuth Client ID: ${GITHUB_CLIENT_ID:-Ov23lisJdUcb1DmKhIfe}"

# Ждем немного для инициализации
sleep 2

# Запускаем сервер
./auth_server