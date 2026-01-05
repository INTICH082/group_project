FROM alpine:3.19

# 1. Устанавливаем все необходимые зависимости
RUN apk update && apk add --no-cache \
    g++ \
    make \
    cmake \
    mysql-dev \
    mariadb-dev \
    mariadb-connector-c-dev \
    curl-dev \
    musl-dev \
    openssl-dev \
    zlib-dev \
    linux-headers

# 2. Устанавливаем рабочую директорию
WORKDIR /app

# 3. Копируем папку authorization со всеми файлами
COPY authorization/ ./authorization/

# 4. Переходим в папку authorization
WORKDIR /app/authorization

# 5. Собираем проект (без использования build.ps1 - используем нативные команды)
RUN mkdir -p build && \
    cd build && \
    cmake .. && \
    make -j$(nproc)

# 6. Проверяем сборку
RUN ls -la build/

# 7. Устанавливаем рабочую директорию для запуска
WORKDIR /app/authorization/build

# 8. Проверяем бинарник
RUN if [ -f "auth.exe" ]; then \
    echo "Build successful!"; \
    echo "Binary size:"; \
    ls -lh auth.exe; \
    else \
    echo "Available files:"; \
    ls -la; \
    echo "Trying to find binary..."; \
    find . -name "*.exe" -o -name "auth*" -type f; \
    exit 1; \
    fi

# 9. Открываем порт (укажите правильный порт из вашего кода)
EXPOSE 8081

# 10. Команда запуска сервера
CMD ["./auth.exe"]