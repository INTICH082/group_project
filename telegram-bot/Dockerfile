FROM python:3.11-slim

# Устанавливаем Node.js если нужен (если проект использует и Python и Node.js)
RUN apt-get update && apt-get install -y curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
COPY package.json .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем Node.js зависимости (если нужны)
RUN npm install

# Копируем остальные файлы проекта
COPY . .

# Создаем не-root пользователя для безопасности
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "bot.py"]