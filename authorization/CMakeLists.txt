cmake_minimum_required(VERSION 3.10)
project(authorization)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CURL REQUIRED)

include_directories("C:/Program Files/MySQL/MySQL Server 9.5/lib")
link_directories("C:/Program Files/MySQL/MySQL Server 9.5/lib")

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