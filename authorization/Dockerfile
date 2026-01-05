FROM ubuntu:22.04

# Установка зависимостей
RUN apt-get update && apt-get install -y \
    g++ \
    make \
    libcurl4-openssl-dev \
    libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем исходники
WORKDIR /app
COPY . .

# Компилируем
RUN g++ -c authorization/database.cpp -Iauthorization -std=c++11
RUN g++ -c authorization/auth.cpp -Iauthorization -std=c++11
RUN g++ -c authorization/server.cpp -Iauthorization -std=c++11
RUN g++ -c authorization/main.cpp -Iauthorization -std=c++11
RUN g++ database.o auth.o server.o main.o -o auth.exe -lmysqlclient -lcurl

# Открываем порт
EXPOSE 8081

# Запускаем сервер
CMD ["./auth.exe"]