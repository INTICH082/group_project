#pragma once
#include <string>
#include <cstdlib>

using namespace std;

namespace Config {
    // Читаем из переменных окружения, если есть, иначе дефолтные значения
    inline string getEnv(const string& key, const string& defaultValue = "") {
        const char* val = getenv(key.c_str());
        return val ? string(val) : defaultValue;
    }

    // GitHub OAuth
    const string GITHUB_CLIENT_ID = getEnv("GITHUB_CLIENT_ID", "Ov23lisJdUcb1DmKhIfe");
    const string GITHUB_CLIENT_SECRET = getEnv("GITHUB_CLIENT_SECRET", "897dbebdde0fcb173d22f45f53de423bb7bb44ac");
    
    // Сервер
    const int PORT = stoi(getEnv("PORT", "8081"));
    
    // База данных
    const string DB_HOST = getEnv("DB_HOST", "127.0.0.1");
    const string DB_USER = getEnv("DB_USER", "root");
    const string DB_PASS = getEnv("DB_PASS", "dbpassiplaygodotandclaimfun");
    const string DB_NAME = getEnv("DB_NAME", "Project");
    
    // JWT
    const string JWT_SECRET = getEnv("JWT_SECRET", "iplaygodotandclaimfun");
    
    // Токены
    const int ACCESS_TOKEN_EXPIRE_SEC = 900;       // 15 минут
    const int REFRESH_TOKEN_EXPIRE_SEC = 2592000;  // 30 дней
}