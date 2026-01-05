#pragma once
#include <string>

using namespace std;

namespace Config {
    // GitHub OAuth
    const string GITHUB_CLIENT_ID = "Ov23lisJdUcb1DmKhIfe";
    const string GITHUB_CLIENT_SECRET = "897dbebdde0fcb173d22f45f53de423bb7bb44ac"; 
    
    // Сервер
    const int PORT = 8081;
    
    // База данных
    const string DB_HOST = "127.0.0.1";
    const string DB_USER = "root";
    const string DB_PASS = "dbpassiplaygodotandclaimfun";
    const string DB_NAME = "Project";
    
    // Секрет для токенов
    const string JWT_SECRET = "iplaygodotandclaimfun";
    
    // JWT настройки
    const int ACCESS_TOKEN_EXPIRE_SEC = 900;    // 15 минут
    const int REFRESH_TOKEN_EXPIRE_SEC = 2592000; // 30 дней
    const int LOGIN_TOKEN_EXPIRE_SEC = 300;     // 5 минут для токена входа
}