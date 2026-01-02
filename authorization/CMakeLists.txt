cmake_minimum_required(VERSION 3.10)
project(authorization)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_TOOLCHAIN_FILE "C:/Users/KSK-SHOP/projects/group_project/group_project/vcpkg/scripts/buildsystems/vcpkg.cmake" CACHE STRING "")

find_package(CURL REQUIRED)

include_directories(
    ${CURL_INCLUDE_DIRS}
    ${CMAKE_CURRENT_SOURCE_DIR}             
    ${CMAKE_CURRENT_SOURCE_DIR}/Crow/include 
    ${CMAKE_CURRENT_SOURCE_DIR}/asio
    ${CMAKE_CURRENT_SOURCE_DIR}/jwt-cpp/include
    "C:/Program Files/MySQL/MySQL Server 9.5/include"
)

add_executable(auth_server
    main.cpp
    auth.cpp
    database.cpp
    utils.cpp
)

target_link_libraries(auth_server
    PRIVATE
    ${CURL_LIBRARIES}
    "C:/Program Files/MySQL/MySQL Server 9.5/lib/mysqlclient.lib"   # ← оставляем .lib для импорта
    ws2_32
    pthread
)

# Важно: говорим, что .dll будет в PATH или рядом с .exe
set_target_properties(auth_server PROPERTIES
    LINK_FLAGS "-Wl,--enable-auto-import"
)