#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#endif

#include <crow.h>
#include "config.hpp"
#include "handlers.hpp"

using namespace std;

Config cfg;

int main() {
    init_mongo_ttl();

    crow::SimpleApp app;
    register_routes(app);
    app.port(cfg.server_port).multithreaded().run();
    return 0;
}