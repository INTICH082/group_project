cmake_minimum_required(VERSION 3.15)
project(auth LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
    set(CMAKE_TOOLCHAIN_FILE "C:/tools/vcpkg/scripts/buildsystems/vcpkg.cmake" CACHE STRING "")
endif()

find_package(Crow CONFIG REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)

# НЕ используем find_package для MySQL — он не предоставляет config
# Вместо этого вручную включаем директории и линкуем библиотеку

include_directories("C:/tools/vcpkg/installed/x64-windows/include")
link_directories("C:/tools/vcpkg/installed/x64-windows/lib")

add_executable(auth main.cpp utils.cpp)

target_link_libraries(auth PRIVATE
    Crow::Crow
    libmysql                              # ← Просто имя библиотеки
    OpenSSL::SSL OpenSSL::Crypto
    nlohmann_json::nlohmann_json
)

if(WIN32)
    target_link_libraries(auth PRIVATE ws2_32 wsock32 mswsock)
endif()