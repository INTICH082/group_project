#pragma once

#include <string>

using namespace std;

struct Config {
    string mongo_uri            = "mongodb://127.0.0.1:27017";
    string db_name              = "test_system";

    string jwt_secret           = "iplaygodotandclaimfun";

    string github_client_id     = "Ov23lisJdUcb1DmKhIfe";        
    string github_client_secret = "897dbebdde0fcb173d22f45f53de423bb7bb44ac";      
    string yandex_client_id     = "da6f89d2c76d4d3b8f4f1e2b3c4d5e6f"; // ← заменить
    string yandex_client_secret = "yandex-secret-placeholder";      // ← заменить

    string redirect_uri         = "http://localhost:18080/callback";

    int    server_port          = 18080;
};

extern Config cfg;