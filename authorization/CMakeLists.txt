cmake_minimum_required(VERSION 3.15)
project(authorization LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Crow CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)
find_package(jwt-cpp CONFIG REQUIRED)
find_package(mongocxx CONFIG REQUIRED)
find_package(OpenSSL REQUIRED)

add_executable(auth
    main.cpp
    handlers.cpp
    utils.cpp
    jwt.cpp
    mongo.cpp
)

target_link_libraries(auth PRIVATE
    Crow::Crow
    nlohmann_json::nlohmann_json
    jwt-cpp::jwt-cpp
    OpenSSL::SSL 
    OpenSSL::Crypto
    $<IF:$<TARGET_EXISTS:mongo::bsoncxx_static>,mongo::bsoncxx_static,mongo::bsoncxx_shared>
    $<IF:$<TARGET_EXISTS:mongo::mongocxx_static>,mongo::mongocxx_static,mongo::mongocxx_shared>
)

# Фикс для MinGW: отключить dllimport для mongo-cxx
target_compile_definitions(auth PRIVATE
    BSONCXX_STATIC
    MONGOCXX_STATIC
)

# Для Windows: WinSock + расширения
if (WIN32)
    target_link_libraries(auth PRIVATE ws2_32 wsock32 mswsock)
endif()

# Include для mongo
target_include_directories(auth PRIVATE ${MONGO_CXX_DRIVER_INCLUDES})