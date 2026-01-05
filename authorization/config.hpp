#pragma once
#include <cstdlib>
#include <string>

using namespace std;

struct Config {
    string mysql_host = "127.0.0.1";
    string mysql_user = "root";
    string mysql_password = "de0fcb173d22f45f53de42";  
    string mysql_db = "Project";
    unsigned int mysql_port = 3306;
    int server_port = 18080;
    string jwt_secret = getenv("JWT_SECRET") ? getenv("JWT_SECRET") : "iplaygodotandclaimfun";
    string github_client_id = "Ov23lisJdUcb1DmKhIfe"; 
    string github_client_secret = "897dbebdde0fcb173d22f45f53de423bb7bb44ac";  
    string yandex_client_id = "da6f89d2c76d4d3b8f4f1e2b3c4d5e6f";  // Замени
    string yandex_client_secret = "yandex-secret-placeholder";  // Замени
    string redirect_uri = "http://localhost:18080/callback";
};

extern Config cfg;