FROM python:3.11-alpine

WORKDIR /app

# Устанавливаем системные зависимости
RUN apk add --no-cache gcc musl-dev linux-headers postgresql-dev

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем код бота и .env (исправлено: копируем в /app)
COPY bot.py .
COPY .env.docker ./.env  # Если файл .env.docker — копируем и переименовываем в .env

# Создаем не-root пользователя
RUN adduser -D -u 1000 botuser && \
    chown -R botuser:botuser /app
USER botuser

# Запускаем бота
CMD ["python", "-u", "bot.py"]