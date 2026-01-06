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

# Создаем пользователя и рабочую директорию
RUN useradd -m -u 1000 appuser
USER appuser
WORKDIR /home/appuser/app

# Копируем исходный код
COPY --chown=appuser:appuser authorization/*.h authorization/*.cpp ./

# Компилируем проект
RUN g++ -c database.cpp -std=c++11
RUN g++ -c auth.cpp -std=c++11
RUN g++ -c server.cpp -std=c++11
RUN g++ -c main.cpp -std=c++11
RUN g++ database.o auth.o server.o main.o -o auth_server -lmysqlclient -lcurl -lpthread

# Открываем порт
EXPOSE 8081

# Запускаем сервер
CMD ["./auth_server"]