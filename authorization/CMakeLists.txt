cmake_minimum_required(VERSION 3.10)
project(authorization)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_TOOLCHAIN_FILE "C:/Users/KSK-SHOP/projects/group_project/group_project/vcpkg/scripts/buildsystems/vcpkg.cmake" CACHE STRING "")

set(CURL_INCLUDE_DIRS "C:/Users/KSK-SHOP/projects/group_project/group_project/vcpkg/installed/x64-mingw-static/include")
set(CURL_LIBRARIES "C:/Users/KSK-SHOP/projects/group_project/group_project/vcpkg/installed/x64-mingw-static/lib/libcurl.a")

# CURL из vcpkg (это работает)
find_package(CURL REQUIRED)
find_package(OpenSSL REQUIRED)

include_directories(
    ${CURL_INCLUDE_DIRS}
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/asio
    ${CMAKE_CURRENT_SOURCE_DIR}/Crow/include
    ${CMAKE_CURRENT_SOURCE_DIR}/jwt-cpp/include
    "C:/MySQL-8.0.35/mysql-8.0.35-winx64/include"
    ${OPENSSL_INCLUDE_DIR}
)

add_executable(auth_server
    main.cpp
    auth.cpp
    database.cpp
    utils.cpp
)

target_link_libraries(auth_server
    PRIVATE
    ${CURL_LIBRARIES}                              # CURL из vcpkg
    ${CURL_INCLUDE_DIRS}
    "C:/MySQL-8.0.35/mysql-8.0.35-winx64/lib/libmysql.lib"
    mswsock
    ws2_32
    pthread
    ${OPENSSL_LIBRARIES}
)