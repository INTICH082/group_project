#include "server.h"
#include "auth.h"
#include <iostream>
#include <sstream>
#include <map>

using namespace std;

// Парсинг параметров из тела запроса
map<string, string> parseParams(const string& body) {
    map<string, string> params;
    stringstream ss(body);
    string pair;
    
    while (getline(ss, pair, '&')) {
        size_t eq = pair.find('=');
        if (eq != string::npos) {
            string key = pair.substr(0, eq);
            string value = pair.substr(eq + 1);
            
            // Декодирование URL (упрощенно)
            size_t pos;
            while ((pos = value.find("%20")) != string::npos) {
                value.replace(pos, 3, " ");
            }
            while ((pos = value.find("%40")) != string::npos) {
                value.replace(pos, 3, "@");
            }
            
            params[key] = value;
        }
    }
    
    return params;
}

int main() {
    Server server;
    
    // Регистрация
    server.post("/api/register", [](const string& body, string& response) {
        auto params = parseParams(body);
        
        string fullname = params["fullname"];
        string email = params["email"];
        int course = params.count("course") ? stoi(params["course"]) : 0;
        string password = params["password"];
        string role = params.count("role") ? params["role"] : "student";
        
        response = Auth::registerUser(fullname, email, course, password, role);
    });
    
    // Вход
    server.post("/api/login", [](const string& body, string& response) {
        auto params = parseParams(body);
        
        string email = params["email"];
        string password = params["password"];
        
        response = Auth::login(email, password);
    });
    
    // Телеграм
    server.post("/api/telegram", [](const string& body, string& response) {
        auto params = parseParams(body);
        
        long long telegram_id = stoll(params["telegram_id"]);
        string first_name = params["first_name"];
        string last_name = params.count("last_name") ? params["last_name"] : "";
        
        response = Auth::telegramAuth(telegram_id, first_name, last_name);
    });
    
    // GitHub
    server.post("/api/github", [](const string& body, string& response) {
        auto params = parseParams(body);
        
        string github_id = params["github_id"];
        string name = params["name"];
        
        response = Auth::githubAuth(github_id, name);
    });
    
    // Яндекс
    server.post("/api/yandex", [](const string& body, string& response) {
        auto params = parseParams(body);
        
        string yandex_id = params["yandex_id"];
        string name = params["name"];
        
        response = Auth::yandexAuth(yandex_id, name);
    });
    
    // Проверка токена
    server.get("/api/me", [](const string& body, string& response) {
        // В реальном сервере токен брался бы из заголовков
        // Здесь для простоты из параметров
        auto params = parseParams(body);
        
        string token = params["token"];
        
        int user_id;
        string email, role;
        
        if (Auth::validateToken(token, user_id, email, role)) {
            response = "{\"user_id\":" + to_string(user_id) + 
                      ",\"email\":\"" + email + 
                      "\",\"role\":\"" + role + "\"}";
        } else {
            response = "{\"error\":\"Invalid token\"}";
        }
    });
    
    server.start(8080);
    return 0;
}