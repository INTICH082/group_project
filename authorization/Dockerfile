FROM ubuntu:22.04

RUN apt-get update && apt-get install -y build-essential cmake git curl wget unzip libssl-dev libcurl4-openssl-dev libmysqlclient-dev

RUN git clone https://github.com/microsoft/vcpkg.git /vcpkg && /vcpkg/bootstrap-vcpkg.sh && /vcpkg/vcpkg install curl:x64-linux mysql-connector-cpp:x64-linux

WORKDIR /app
COPY . /app

RUN mkdir build && cd build && cmake .. -DCMAKE_TOOLCHAIN_FILE=/vcpkg/scripts/buildsystems/vcpkg.cmake -DCMAKE_BUILD_TYPE=Release && make

CMD ["./build/auth_server"]