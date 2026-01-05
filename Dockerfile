# Dockerfile
FROM alpine:latest

# Устанавливаем зависимости для MySQL Connector/C
RUN apk add --no-cache \
    g++ \
    make \
    cmake \
    curl-dev \
    mysql-client \
    mysql-dev \
    mysql-connector-c \
    mysql-connector-c-dev \
    musl-dev

# Альтернатива: используем MySQL Connector/C из исходников
RUN apk add --no-cache wget tar && \
    wget https://dev.mysql.com/get/Downloads/Connector-C/mysql-connector-c-8.0.33-linux-glibc2.28-x86_64.tar.gz && \
    tar -xzf mysql-connector-c-8.0.33-linux-glibc2.28-x86_64.tar.gz && \
    mv mysql-connector-c-8.0.33-linux-glibc2.28-x86_64 /usr/local/mysql && \
    rm mysql-connector-c-8.0.33-linux-glibc2.28-x86_64.tar.gz

# Устанавливаем переменные окружения для компиляции
ENV MYSQL_INCLUDE_DIR=/usr/include/mariadb
ENV MYSQL_LIB_DIR=/usr/lib

# Создаем рабочую директорию
WORKDIR /app

# Копируем исходники
COPY authorization/ ./authorization/

# Компилируем с правильными путями
RUN cd authorization && \
    g++ -c database.cpp -I. -I/usr/include/mariadb -std=c++11 && \
    g++ -c auth.cpp -I. -I/usr/include/mariadb -std=c++11 && \
    g++ -c server.cpp -I. -I/usr/include/mariadb -std=c++11 && \
    g++ -c main.cpp -I. -I/usr/include/mariadb -std=c++11 && \
    g++ database.o auth.o server.o main.o -o auth.exe \
        -L/usr/lib -lmariadb -lcurl

# Открываем порт
EXPOSE 8081

# Запускаем сервер
CMD ["/group_project/authorization/auth.exe"]