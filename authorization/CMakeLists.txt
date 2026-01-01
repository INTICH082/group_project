cmake_minimum_required(VERSION 3.10)
project(authorization)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_PREFIX_PATH "${CMAKE_PREFIX_PATH};C:/Users/KSK-SHOP/projects/group_project/group_project/vcpkg/installed/x64-windows")
set(CURL_DIR "C:/Users/KSK-SHOP/projects/group_project/group_project/vcpkg/installed/x64-windows/share/curl")

find_package(CURL REQUIRED)

# Подключаем MySQL C API (libmysql)
include_directories("C:/Program Files/MySQL/MySQL Server 9.5/include")
link_directories("C:/Program Files/MySQL/MySQL Server 9.5/lib")

# Добавляем текущую папку для crow_all.h и других локальных заголовков
include_directories(${CMAKE_CURRENT_SOURCE_DIR} jwt-cpp/include)

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