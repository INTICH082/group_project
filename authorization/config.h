#pragma once
#include <string>

using namespace std;

namespace Config {
    const string DB_HOST = "localhost";
    const string DB_USER = "root";
    const string DB_PASS = "";
    const string DB_NAME = "Project";
    const string JWT_SECRET = "iplaygodotandclaimfun";
    const int JWT_EXPIRE = 3600 * 24 * 30; // 30 дней
}