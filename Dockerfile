FROM python:3.11-slim

WORKDIR /app

# Устанавливаем минимальные системные зависимости (только если нужны для сборки wheels)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc6-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем код бота и .env
COPY bot.py .
COPY .env .

# Создаем не-root пользователя
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app
USER botuser

# Запускаем бота
CMD ["python", "-u", "bot.py"]