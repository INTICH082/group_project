#include "auth.h"
#include "database.h"
#include "config.h"
#include <curl/curl.h>
#include <ctime>
#include <sstream>
#include <iostream>
#include <algorithm>
#include <cstdlib>
using namespace std;

// Callback для curl
static size_t writeCallback(void* data, size_t size, size_t nmemb, void* userp) {
    string* str = (string*)userp;
    str->append((char*)data, size * nmemb);
    return size * nmemb;
}

bool Auth::init() {
    curl_global_init(CURL_GLOBAL_ALL);
    return Database::connect();
}

void Auth::cleanup() {
    Database::close();
    curl_global_cleanup();
}

string Auth::homePage() {
    string url = "https://github.com/login/oauth/authorize?client_id=" + 
                Config::GITHUB_CLIENT_ID + "&redirect_uri=http://localhost:" + 
                to_string(Config::PORT) + "/auth/callback";
    
    return R"(<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Авторизация</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .btn { padding: 12px 24px; background: #1d2125ff; color: white; 
               text-decoration: none; border-radius: 6px; display: inline-block; }
        .box { background: #f5f5f5; padding: 20px; margin: 20px 0; border-radius: 8px; }
        pre { background: #2d2d2d; color: white; padding: 15px; border-radius: 5px; }
        code { background: #e9ecef; padding: 2px 6px; border-radius: 4px; }
    </style>
</head>
<body>
    <h1>🔐 Авторизация</h1>
    <p>Студенческий проект - GitHub OAuth + Telegram API</p>
    
    <div style="text-align: center; margin: 30px 0;">
        <a href=")" + url + R"(" class="btn">Войти через GitHub</a>
    </div>
    
    <div class="box">
        <h3>🤖 Telegram API</h3>
        <p><strong>POST /api/telegram</strong></p>
        <p>Параметры (form-data):</p>
        <ul>
            <li><code>telegram_id</code> - ID пользователя в Telegram</li>
            <li><code>name</code> - Имя пользователя</li>
        </ul>
        <p>Пример cURL:</p>
        <pre>curl -X POST http://localhost:8081/api/telegram ^
  -d "telegram_id=123456789" ^
  -d "name=Иван Иванов"</pre>
    </div>
    
    <div class="box">
        <h3>🔍 Проверка токена</h3>
        <p><strong>GET /api/verify?token=ВАШ_ТОКЕН</strong></p>
        <p>Пример:</p>
        <pre>curl "http://localhost:8081/api/verify?token=123|456|789"</pre>
    </div>
    
    <div class="box">
        <h3>🆕 Новое API (для Web Client/Bot Logic)</h3>
        <p><strong>GET /auth?login_token=TOKEN</strong> - Получить URL для OAuth</p>
        <p><strong>POST /auth/refresh</strong> - Обновить токены (тело: refresh_token=TOKEN)</p>
        <p><strong>GET /auth/verify?token=TOKEN</strong> - Проверить access token</p>
    </div>
</body>
</html>)";
}

string Auth::getGitHubToken(const string& code) {
    CURL* curl = curl_easy_init();
    string response;
    
    if (curl) {
        string data = "client_id=" + Config::GITHUB_CLIENT_ID +
                     "&client_secret=" + Config::GITHUB_CLIENT_SECRET +
                     "&code=" + code;
        
        curl_easy_setopt(curl, CURLOPT_URL, "https://github.com/login/oauth/access_token");
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, data.c_str());
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
        
        curl_easy_perform(curl);
        curl_easy_cleanup(curl);
    }
    
    size_t pos = response.find("access_token=");
    if (pos != string::npos) {
        size_t end = response.find('&', pos);
        if (end == string::npos) end = response.length();
        return response.substr(pos + 13, end - pos - 13);
    }
    
    return "";
}

string Auth::getGitHubUser(const string& token) {
    CURL* curl = curl_easy_init();
    string response;
    
    if (curl) {
        struct curl_slist* headers = nullptr;
        headers = curl_slist_append(headers, ("Authorization: token " + token).c_str());
        headers = curl_slist_append(headers, "User-Agent: StudentProject");
        
        curl_easy_setopt(curl, CURLOPT_URL, "https://api.github.com/user");
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
        
        curl_easy_perform(curl);
        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
    }
    
    return response;
}

string Auth::parseJson(const string& json, const string& key) {
    size_t pos = json.find("\"" + key + "\":");
    if (pos == string::npos) return "";
    
    size_t start = json.find("\"", pos + key.length() + 3);
    if (start == string::npos) return "";
    
    size_t end = json.find("\"", start + 1);
    if (end == string::npos) return "";
    
    return json.substr(start + 1, end - start - 1);
}

string Auth::createToken(const string& data, int expire_seconds) {
    // Добавляем timestamp
    time_t now = time(nullptr);
    string full_data = data + "|" + to_string(now);
    
    // Простая подпись
    unsigned long hash = 5381;
    for (char c : full_data + Config::JWT_SECRET) {
        hash = ((hash << 5) + hash) + c;
    }
    
    return full_data + "|" + to_string(hash);
}

bool Auth::parseToken(const string& token, int& user_id, string& type, time_t& created_at) {
    size_t pos1 = token.find('|');
    size_t pos2 = token.find('|', pos1 + 1);
    size_t pos3 = token.find('|', pos2 + 1);
    
    if (pos1 == string::npos || pos2 == string::npos || pos3 == string::npos) {
        return false;
    }
    
    string id_str = token.substr(0, pos1);
    type = token.substr(pos1 + 1, pos2 - pos1 - 1);
    string time_str = token.substr(pos2 + 1, pos3 - pos2 - 1);
    string hash_str = token.substr(pos3 + 1);
    
    // Проверка подписи
    string check_data = id_str + "|" + type + "|" + time_str;
    unsigned long check_hash = 5381;
    for (char c : check_data + Config::JWT_SECRET) {
        check_hash = ((check_hash << 5) + check_hash) + c;
    }
    
    if (to_string(check_hash) != hash_str) {
        return false;
    }
    
    try {
        user_id = stoi(id_str);
        created_at = stoll(time_str);
        return true;
    } catch (...) {
        return false;
    }
}

bool checkToken(const string& token, int& user_id) {
    string type;
    time_t created_at = 0;
    
    if (!Auth::parseToken(token, user_id, type, created_at)) {
        return false;
    }
    
    // Проверяем тип токена (должен быть "access")
    if (type != "access") {
        return false;
    }
    
    // Проверяем срок действия
    if (time(nullptr) - created_at > Config::ACCESS_TOKEN_EXPIRE_SEC) {
        return false;
    }
    
    return true;
}

string Auth::generateTokenPair(int user_id) {
    time_t now = time(nullptr);
    
    // Access token (короткоживущий)
    string access_data = to_string(user_id) + "|access|" + to_string(now);
    string access_token = createToken(access_data, Config::ACCESS_TOKEN_EXPIRE_SEC);
    
    // Refresh token (долгоживущий)
    string refresh_data = to_string(user_id) + "|refresh|" + to_string(now);
    string refresh_token = createToken(refresh_data, Config::REFRESH_TOKEN_EXPIRE_SEC);
    
    return "{\"access_token\":\"" + access_token + 
           "\",\"refresh_token\":\"" + refresh_token + 
           "\",\"user_id\":" + to_string(user_id) + 
           ",\"expires_in\":" + to_string(Config::ACCESS_TOKEN_EXPIRE_SEC) + "}";
}

string Auth::verifyToken(const string& token) {
    int user_id = 0;
    if (checkToken(token, user_id)) {
        return "{\"valid\":true,\"user_id\":" + to_string(user_id) + "}";
    }
    return "{\"valid\":false}";
}

string Auth::telegramAuth(const string& telegram_id_str, const string& name) {
    if (telegram_id_str.empty() || name.empty()) {
        return "{\"error\":\"telegram_id and name required\"}";
    }
    
    // Проверка что telegram_id - число
    if (!all_of(telegram_id_str.begin(), telegram_id_str.end(), ::isdigit)) {
        return "{\"error\":\"telegram_id must be a number\"}";
    }
    
    long long telegram_id = stoll(telegram_id_str);
    
    int user_id = Database::getUserByTelegramId(telegram_id);
    if (user_id == 0) {
        string email = "tg" + to_string(telegram_id) + "@telegram.user";
        user_id = Database::createUser(name, email, "", telegram_id);
    }
    
    if (user_id == 0) {
        return "{\"error\":\"Database error\"}";
    }
    
    // Используем новую генерацию токенов
    return generateTokenPair(user_id);
}

// ========== TokenManager реализация ==========
map<string, int> TokenManager::loginTokens;
map<string, time_t> TokenManager::tokenExpiry;

string TokenManager::createLoginToken(int user_id) {
    cleanupExpiredTokens();
    
    // Генерируем случайный токен
    srand(static_cast<unsigned int>(time(nullptr)));  // ИСПРАВЛЕНО: преобразование типа
    string random_part = to_string(rand() % 1000000);
    string token_str = "login_" + to_string(user_id) + "_" + random_part + "_" + to_string(time(nullptr));
    
    // Простой hash для уникальности
    unsigned long hash = 5381;
    for (char c : token_str) hash = ((hash << 5) + hash) + c;
    token_str = to_string(hash);
    
    loginTokens[token_str] = user_id;
    tokenExpiry[token_str] = time(nullptr) + Config::LOGIN_TOKEN_EXPIRE_SEC;
    
    return token_str;
}

int TokenManager::validateLoginToken(const string& token) {
    cleanupExpiredTokens();
    
    auto it = loginTokens.find(token);
    if (it != loginTokens.end()) {
        int user_id = it->second;
        loginTokens.erase(it);
        tokenExpiry.erase(token);
        return user_id;
    }
    return 0;
}

void TokenManager::cleanupExpiredTokens() {
    time_t now = time(nullptr);
    for (auto it = tokenExpiry.begin(); it != tokenExpiry.end(); ) {
        if (it->second < now) {
            loginTokens.erase(it->first);
            it = tokenExpiry.erase(it);
        } else {
            ++it;
        }
    }
}

// ========== Новые методы Auth ==========

string Auth::startOAuth(const string& login_token) {
    if (login_token.empty()) {
        return "{\"error\":\"login_token required\"}";
    }
    
    // Проверяем, что токен существует
    int user_id = 999; // Временный ID
    
    // Создаём новый токен для OAuth процесса
    string state_token = TokenManager::createLoginToken(user_id);
    
    // ПРАВИЛЬНО СОБРАННЫЙ URL:
    string url = "https://github.com/login/oauth/authorize?" +
                 string("client_id=") + Config::GITHUB_CLIENT_ID +
                 "&redirect_uri=http://localhost:" + to_string(Config::PORT) + "/auth/callback" +
                 "&state=" + state_token +
                 "&scope=user";
    
    return "{\"auth_url\":\"" + url + "\", \"state_token\":\"" + state_token + "\"}";
}

string Auth::handleGitHubCallback(const string& code, const string& state) {
    // state = наш login_token
    int user_id = TokenManager::validateLoginToken(state);
    if (user_id == 0) {
        return "{\"error\":\"Invalid or expired login token\"}";
    }
    
    // Получаем access_token от GitHub
    string gh_token = getGitHubToken(code);
    if (gh_token.empty()) {
        return "{\"error\":\"GitHub auth failed\"}";
    }
    
    // Получаем данные пользователя от GitHub
    string user_info = getGitHubUser(gh_token);
    string github_id = parseJson(user_info, "id");
    string login = parseJson(user_info, "login");
    string name = parseJson(user_info, "name");
    
    if (github_id.empty()) {
        return "{\"error\":\"Invalid user info from GitHub\"}";
    }
    
    if (name.empty()) name = login;
    
    // Проверяем, есть ли уже пользователь с таким github_id
    int existing_id = Database::getUserByGithubId(github_id);
    if (existing_id == 0) {
        // Создаём нового пользователя
        string email = login + "@github.user";
        existing_id = Database::createUser(name, email, github_id, 0);
        
        if (existing_id == 0) {
            return "{\"error\":\"Database error creating user\"}";
        }
        user_id = existing_id;
    } else {
        user_id = existing_id;
    }
    
    // Генерируем JWT пару
    return generateTokenPair(user_id);
}

string Auth::refreshToken(const string& refresh_token) {
    int user_id = 0;
    string type;
    time_t created_at = 0;
    
    // Парсим токен
    if (!parseToken(refresh_token, user_id, type, created_at)) {
        return "{\"error\":\"Invalid refresh token\"}";
    }
    
    // Проверяем тип
    if (type != "refresh") {
        return "{\"error\":\"Not a refresh token\"}";
    }
    
    // Проверяем срок действия
    if (time(nullptr) - created_at > Config::REFRESH_TOKEN_EXPIRE_SEC) {
        return "{\"error\":\"Refresh token expired\"}";
    }
    
    // Генерируем новую пару
    return generateTokenPair(user_id);
}