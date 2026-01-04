cmake_minimum_required(VERSION 3.15)
project(authorization CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Crow CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)
find_package(jwt-cpp CONFIG REQUIRED)
find_package(mongocxx CONFIG REQUIRED)
find_package(OpenSSL REQUIRED)

add_executable(auth main.cpp)

target_link_libraries(auth PRIVATE
    Crow::Crow
    nlohmann_json::nlohmann_json
    jwt-cpp::jwt-cpp
    mongo::bson_shared 
    mongo::mongocxx_shared
    OpenSSL::SSL 
    OpenSSL::Crypto
)

target_include_directories(auth PRIVATE ${MONGO_CXX_DRIVER_INCLUDES})