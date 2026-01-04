#include <crow.h>
#include "config.hpp"
#include "handlers.hpp"

using namespace std;

Config cfg;

int main() {
    crow::SimpleApp app;
    register_routes(app);
    app.port(cfg.server_port).multithreaded().run();
    return 0;
}