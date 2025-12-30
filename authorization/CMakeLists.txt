cmake_minimum_required(VERSION 3.10)
project(authorization)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CURL REQUIRED)
find_package(mysql-connector-cpp REQUIRED)

include_directories(${CURL_INCLUDE_DIRS} jwt-cpp/include)

add_executable(auth_server
    main.cpp
    auth.cpp
    database.cpp
    utils.cpp
)

target_link_libraries(auth_server
    ${CURL_LIBRARIES}
    mysql-connector-cpp::mysql-connector-cpp
    pthread
)