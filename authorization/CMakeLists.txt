cmake_minimum_required(VERSION 3.10)
project(authorization)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CURL REQUIRED)

# Подключаем MySQL C API (libmysql)
include_directories("C:/Program Files/MySQL/MySQL Server 9.5/include")
link_directories("C:/Program Files/MySQL/MySQL Server 9.5/lib")

# Добавляем текущую папку — здесь лежит crow_all.h и asio/
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/asio
    jwt-cpp/include
)

add_executable(auth_server
    main.cpp
    auth.cpp
    database.cpp
    utils.cpp
)

target_link_libraries(auth_server
    ${CURL_LIBRARIES}
    mysqlclient
    pthread
)