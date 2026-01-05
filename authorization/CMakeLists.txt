cmake_minimum_required(VERSION 3.15)
project(authorization LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
    set(CMAKE_TOOLCHAIN_FILE "C:/tools/vcpkg/scripts/buildsystems/vcpkg.cmake" CACHE STRING "")
endif()

find_package(Crow CONFIG REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)
find_package(jwt-cpp CONFIG REQUIRED)
find_package(cpr CONFIG REQUIRED)
find_package(libmysql CONFIG REQUIRED)  # ← Это правильный пакет

add_executable(authorization main.cpp handlers.cpp utils.cpp jwt.cpp mysql.cpp)

include_directories(C:/mysql-headers)

target_link_libraries(authorization PRIVATE
    Crow::Crow
    unofficial::libmysql::libmysql  # ← Таргет из vcpkg (unofficial — нормально)
    OpenSSL::SSL OpenSSL::Crypto
    nlohmann_json::nlohmann_json
    jwt-cpp::jwt-cpp
    cpr::cpr
)

target_compile_definitions(authorization PRIVATE NOMINMAX _HAS_STD_BYTE=0)

if(WIN32)
    target_link_libraries(authorization PRIVATE ws2_32 wsock32 mswsock)
endif()