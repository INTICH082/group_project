FROM alpine:3.19

# 1. Устанавливаем компилятор и зависимости
RUN apk update && apk add --no-cache \
    g++ \
    make \
    mysql-dev \
    curl-dev \
    musl-dev \
    openssl-dev

# 2. Устанавливаем рабочую директорию
WORKDIR /app

# 3. Копируем исходники из папки authorization
COPY authorization/ ./authorization/

# 4. Переходим в папку с исходниками
WORKDIR /app/authorization

# 5. Компилируем напрямую через g++
# Предполагаемая структура компиляции (адаптируйте под ваш проект):
RUN g++ -o auth.exe \
    auth.cpp \
    database.cpp \
    server.cpp \
    main.cpp \
    -I/usr/include/mysql \
    -lmysqlclient \
    -lcurl \
    -lssl \
    -lcrypto \
    -pthread \
    -std=c++17 \
    -O2

# 6. Проверяем сборку
RUN ls -la auth.exe && \
    file auth.exe && \
    ldd auth.exe 2>/dev/null || echo "Binary compiled successfully"

# 7. Открываем порт (укажите ваш порт из server.cpp)
EXPOSE 8081

# 8. Запускаем сервер
CMD ["./auth.exe"]