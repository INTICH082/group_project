FROM python:3.11-slim

WORKDIR /app

# Системные зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Код
COPY bot.py .

# Без root (рекомендуется)
RUN useradd -m botuser
USER botuser

CMD ["python", "bot.py"]
