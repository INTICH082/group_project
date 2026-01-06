FROM ubuntu:22.04

# Устанавливаем таймзону
ENV TZ=Europe/Moscow
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    g++ \
    curl \
    libcurl4-openssl-dev \
    libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем исходный код
COPY . .

# Патчим код для Linux
RUN sed -i 's/#include <mysql.h>/#include <mysql\/mysql.h>/' authorization/database.cpp

# Компилируем
RUN g++ -c authorization/database.cpp -std=c++11 -I/usr/include/mysql \
    && g++ -c authorization/auth.cpp -std=c++11 -I/usr/include/mysql \
    && g++ -c authorization/server.cpp -std=c++11 -I/usr/include/mysql \
    && g++ -c authorization/main.cpp -std=c++11 -I/usr/include/mysql \
    && g++ database.o auth.o server.o main.o -o auth_server -lmysqlclient -lcurl -lpthread

EXPOSE 8081

CMD ["./auth_server"]