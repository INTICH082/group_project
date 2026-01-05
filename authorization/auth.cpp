#include "auth.h"
#include "database.h"
#include "config.h"
#include <curl/curl.h>
#include <ctime>
#include <sstream>
#include <iostream>
#include <algorithm>
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
                to_string(Config::PORT) + "/auth/github/callback";
    
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
</body>
</html>)";
}

string getGitHubToken(const string& code) {
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
        return response.substr(pos + 13, end - pos - 13);
    }
    
    return "";
}

string getGitHubUser(const string& token) {
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

string parseJson(const string& json, const string& key) {
    size_t pos = json.find("\"" + key + "\":");
    if (pos == string::npos) return "";
    
    size_t start = json.find("\"", pos + key.length() + 3);
    if (start == string::npos) return "";
    
    size_t end = json.find("\"", start + 1);
    if (end == string::npos) return "";
    
    return json.substr(start + 1, end - start - 1);
}

string createToken(int user_id) {
    long long timestamp = time(nullptr);
    string data = to_string(user_id) + "|" + to_string(timestamp);
    
    // Простая подпись
    unsigned long hash = 5381;
    for (char c : data + Config::JWT_SECRET) {
        hash = ((hash << 5) + hash) + c;
    }
    
    return data + "|" + to_string(hash);
}

bool checkToken(const string& token, int& user_id) {
    size_t pos1 = token.find('|');
    size_t pos2 = token.find('|', pos1 + 1);
    
    if (pos1 == string::npos || pos2 == string::npos) return false;
    
    string id_str = token.substr(0, pos1);
    string time_str = token.substr(pos1 + 1, pos2 - pos1 - 1);
    string hash_str = token.substr(pos2 + 1);
    
    // 30 дней
    long long timestamp = stoll(time_str);
    if (time(nullptr) - timestamp > 2592000) return false;
    
    // Проверка подписи
    string check_data = id_str + "|" + time_str;
    unsigned long check_hash = 5381;
    for (char c : check_data + Config::JWT_SECRET) {
        check_hash = ((check_hash << 5) + check_hash) + c;
    }
    
    if (to_string(check_hash) != hash_str) return false;
    
    user_id = stoi(id_str);
    return true;
}

string Auth::githubAuth(const string& code) {
    string token = getGitHubToken(code);
    if (token.empty()) {
        return "{\"error\":\"GitHub auth failed\"}";
    }
    
    string user_info = getGitHubUser(token);
    string github_id = parseJson(user_info, "id");
    string login = parseJson(user_info, "login");
    string name = parseJson(user_info, "name");
    
    if (github_id.empty() || login.empty()) {
        return "{\"error\":\"Invalid user info\"}";
    }
    
    if (name.empty()) name = login;
    
    int user_id = Database::getUserByGithubId(github_id);
    if (user_id == 0) {
        string email = login + "@github.user";
        user_id = Database::createUser(name, email, github_id, 0);
    }
    
    if (user_id == 0) {
        return "{\"error\":\"Database error\"}";
    }
    
    string jwt = createToken(user_id);
    return "{\"token\":\"" + jwt + "\",\"user_id\":" + to_string(user_id) + "}";
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
    
    string jwt = createToken(user_id);
    return "{\"token\":\"" + jwt + "\",\"user_id\":" + to_string(user_id) + "}";
}

string Auth::verifyToken(const string& token) {
    int user_id = 0;
    if (checkToken(token, user_id)) {
        return "{\"valid\":true,\"user_id\":" + to_string(user_id) + "}";
    }
    return "{\"valid\":false}";
}