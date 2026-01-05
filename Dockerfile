FROM alpine:3.19

# 1. Устанавливаем все необходимые зависимости
RUN apk update && apk add --no-cache \
    # Компилятор и инструменты сборки
    g++ \
    make \
    cmake \
    # MySQL зависимости
    mysql-dev \
    mariadb-dev \
    mariadb-connector-c-dev \
    # Сетевые библиотеки
    curl-dev \
    # Системные библиотеки
    musl-dev \
    openssl-dev \
    zlib-dev \
    # Для работы с сервером
    linux-headers

# 2. Устанавливаем рабочую директорию
WORKDIR /app

# 3. Копируем ТОЛЬКО нужные файлы (минимизируем кэш)
# Сначала копируем заголовочные файлы и CMakeLists.txt (если есть)
COPY CMakeLists.txt ./
COPY *.h ./
COPY *.cpp ./
# Копируем скрипт сборки (если нужен)
COPY build.ps1 ./

# 4. Создаем папку build и компилируем проект
RUN mkdir -p build && \
    cd build && \
    # Если есть CMakeLists.txt в корне
    cmake .. -DCMAKE_BUILD_TYPE=Release && \
    make -j$(nproc)

# 5. Проверяем, что бинарник создан
RUN ls -la /app/build/

# 6. Устанавливаем рабочую директорию для запуска
WORKDIR /app/build

# 7. Проверяем зависимости бинарника
RUN ldd auth.exe 2>/dev/null || echo "Binary check completed"

# 8. Открываем порт (уточните какой порт использует ваше приложение)
EXPOSE 8080

# 9. Команда запуска сервера
CMD ["./auth.exe"]