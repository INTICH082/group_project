#pragma once
#include <string>

using namespace std;

namespace Config {
    const string GITHUB_CLIENT_ID = "Ov23lisJdUcb1DmKhIfe";
    const string GITHUB_CLIENT_SECRET = "897dbebdde0fcb173d22f45f53de423bb7bb44ac"; 
    const int PORT = 8081;
    const string DB_HOST = "127.0.0.1";
    const string DB_USER = "root";
    const string DB_PASS = "dbpassiplaygodotandclaimfun";
    const string DB_NAME = "Project";
    const string JWT_SECRET = "iplaygodotandclaimfun";
    const int ACCESS_TOKEN_EXPIRE_SEC = 900;
    const int REFRESH_TOKEN_EXPIRE_SEC = 2592000;
}