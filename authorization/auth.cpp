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

string Auth::hashPassword(const string& password) {
    unsigned long hash = 5381;
    for (char c : password + Config::JWT_SECRET) {
        hash = ((hash << 5) + hash) + c;
    }
    return to_string(hash);
}

bool Auth::verifyPassword(const string& password, const string& hash) {
    return hashPassword(password) == hash;
}

string Auth::registerUser(const string& login, const string& password,
                         const string& fullname, const string& email) {
    if (login.empty() || password.empty() || fullname.empty() || email.empty()) {
        return "{\"error\":\"Все поля обязательны\"}";
    }
    
    if (Database::getUserByLogin(login) != 0) {
        return "{\"error\":\"Логин уже существует\"}";
    }
    
    string password_hash = hashPassword(password);
    int user_id = Database::createUserWithPassword(login, password_hash, fullname, email);
    
    if (user_id == 0) return "{\"error\":\"Ошибка БД\"}";
    return generateTokenPair(user_id);
}

string Auth::loginUser(const string& login, const string& password) {
    if (login.empty() || password.empty()) {
        return "{\"error\":\"Логин и пароль обязательны\"}";
    }
    
    auto user_data = Database::getUserWithPasswordHash(login);
    if (user_data.first == 0 || !verifyPassword(password, user_data.second)) {
        return "{\"error\":\"Неверный логин или пароль\"}";
    }
    
    return generateTokenPair(user_data.first);
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
    time_t now = time(nullptr);
    string full_data = data + "|" + to_string(now);
    
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
    
    string check_data = id_str + "|" + type + "|" + time_str;
    unsigned long check_hash = 5381;
    for (char c : check_data + Config::JWT_SECRET) {
        check_hash = ((check_hash << 5) + check_hash) + c;
    }
    
    if (to_string(check_hash) != hash_str) return false;
    
    user_id = stoi(id_str);
    created_at = stoll(time_str);
    return true;
}

string Auth::generateTokenPair(int user_id) {
    time_t now = time(nullptr);
    
    string access_token = createToken(to_string(user_id) + "|access|" + to_string(now), 
                                     Config::ACCESS_TOKEN_EXPIRE_SEC);
    string refresh_token = createToken(to_string(user_id) + "|refresh|" + to_string(now), 
                                      Config::REFRESH_TOKEN_EXPIRE_SEC);
    
    return "{\"access_token\":\"" + access_token + 
           "\",\"refresh_token\":\"" + refresh_token + 
           "\",\"user_id\":" + to_string(user_id) + 
           ",\"expires_in\":" + to_string(Config::ACCESS_TOKEN_EXPIRE_SEC) + "}";
}

string Auth::verifyToken(const string& token) {
    int user_id = 0;
    string type;
    time_t created_at = 0;
    
    if (!parseToken(token, user_id, type, created_at) || type != "access") {
        return "{\"valid\":false}";
    }
    
    if (time(nullptr) - created_at > Config::ACCESS_TOKEN_EXPIRE_SEC) {
        return "{\"valid\":false}";
    }
    
    return "{\"valid\":true,\"user_id\":" + to_string(user_id) + "}";
}

string Auth::telegramAuth(const string& telegram_id_str, const string& name) {
    if (telegram_id_str.empty() || name.empty()) {
        return "{\"error\":\"Требуется telegram_id и имя\"}";
    }
    
    long long telegram_id = stoll(telegram_id_str);
    int user_id = Database::getUserByTelegramId(telegram_id);
    
    if (user_id == 0) {
        string login = "tg_" + to_string(telegram_id);
        string email = to_string(telegram_id) + "@telegram.user";
        user_id = Database::createTelegramUser(login, name, email, telegram_id);
    }
    
    if (user_id == 0) return "{\"error\":\"Ошибка БД\"}";
    return generateTokenPair(user_id);
}

string Auth::startOAuth(const string& login_token) {
    if (login_token.empty()) {
        return "{\"error\":\"Требуется login_token\"}";
    }
    
    // Проверяем токен и получаем user_id
    int user_id = TokenManager::validateLoginToken(login_token);
    if (user_id == 0) {
        return "{\"error\":\"Неверный login_token\"}";
    }
    
    // Создаем state токен для этого пользователя
    string state_token = TokenManager::createLoginToken(user_id);
    
    string url = "https://github.com/login/oauth/authorize?client_id=" + Config::GITHUB_CLIENT_ID +
                "&redirect_uri=http://localhost:" + to_string(Config::PORT) + "/auth/callback" +
                "&state=" + state_token + "&scope=user";
    
    return "{\"auth_url\":\"" + url + "\", \"state_token\":\"" + state_token + "\"}";
}

string Auth::handleGitHubCallback(const string& code, const string& state) {
    int user_id = TokenManager::validateLoginToken(state);
    if (user_id == 0) return "{\"error\":\"Неверный или устаревший токен\"}";
    
    string gh_token = getGitHubToken(code);
    if (gh_token.empty()) return "{\"error\":\"Ошибка GitHub авторизации\"}";
    
    string user_info = getGitHubUser(gh_token);
    string github_id = parseJson(user_info, "id");
    string login = parseJson(user_info, "login");
    string name = parseJson(user_info, "name");
    string email = parseJson(user_info, "email");
    
    if (github_id.empty()) return "{\"error\":\"Неверные данные от GitHub\"}";
    if (name.empty()) name = login;
    if (email.empty()) email = login + "@github.user";
    
    int existing_id = Database::getUserByGithubId(github_id);
    if (existing_id == 0) {
        existing_id = Database::createGitHubUser(login, name, email, github_id);
        if (existing_id == 0) return "{\"error\":\"Ошибка создания пользователя\"}";
        user_id = existing_id;
    } else {
        user_id = existing_id;
    }
    
    return generateTokenPair(user_id);
}

string Auth::refreshToken(const string& refresh_token) {
    int user_id = 0;
    string type;
    time_t created_at = 0;
    
    if (!parseToken(refresh_token, user_id, type, created_at) || type != "refresh") {
        return "{\"error\":\"Неверный refresh токен\"}";
    }
    
    if (time(nullptr) - created_at > Config::REFRESH_TOKEN_EXPIRE_SEC) {
        return "{\"error\":\"Refresh токен устарел\"}";
    }
    
    return generateTokenPair(user_id);
}

map<string, int> TokenManager::loginTokens;

string TokenManager::createLoginToken(int user_id) {
    cleanupExpiredTokens();
    
    srand(static_cast<unsigned int>(time(nullptr)));
    string token_str = "login_" + to_string(user_id) + "_" + 
                      to_string(rand() % 1000000) + "_" + 
                      to_string(time(nullptr));
    
    unsigned long hash = 5381;
    for (char c : token_str) hash = ((hash << 5) + hash) + c;
    token_str = to_string(hash);
    
    loginTokens[token_str] = user_id;
    return token_str;
}

int TokenManager::validateLoginToken(const string& token) {
    auto it = loginTokens.find(token);
    if (it != loginTokens.end()) {
        int user_id = it->second;
        loginTokens.erase(it);
        return user_id;
    }
    return 0;
}

void TokenManager::cleanupExpiredTokens() {
    static int counter = 0;
    if (++counter % 10 == 0) {
        loginTokens.clear();
    }
}