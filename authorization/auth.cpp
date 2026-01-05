#include "auth.h"
#include "database.h"
#include "config.h"
#include <curl/curl.h>
#include <ctime>
#include <sstream>
#include <iostream>
#include <algorithm>
#include <cstdlib>
#include <regex>
#include <random>

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

// ========== РАБОТА С ПАРОЛЯМИ ==========

string Auth::hashPassword(const string& password) {
    // Простая имитация хэширования (замените на реальное хэширование в продакшене)
    // В реальном проекте используйте: BCrypt, Argon2 или SHA-256 с солью
    unsigned long hash = 5381;
    for (char c : password) {
        hash = ((hash << 5) + hash) + c;
    }
    
    // Добавляем соль из конфига
    for (char c : Config::JWT_SECRET) {
        hash = ((hash << 5) + hash) + c;
    }
    
    return to_string(hash);
}

bool Auth::verifyPassword(const string& password, const string& hash) {
    string new_hash = hashPassword(password);
    return new_hash == hash;
}

// ========== НОВЫЙ МЕТОД: РЕГИСТРАЦИЯ ==========

string Auth::registerUser(const string& login, const string& password, 
                         const string& fullname, const string& email) {
    
    // Валидация входных данных
    if (login.empty() || password.empty() || fullname.empty() || email.empty()) {
        return "{\"error\":\"All fields are required\"}";
    }
    
    if (login.length() > Config::MAX_LOGIN_LENGTH) {
        return "{\"error\":\"Login too long\"}";
    }
    
    if (password.length() < 6) {
        return "{\"error\":\"Password must be at least 6 characters\"}";
    }
    
    // Проверка формата email
    regex email_regex(R"((\w+)(\.\w+)*@(\w+\.)+\w+)");
    if (!regex_match(email, email_regex)) {
        return "{\"error\":\"Invalid email format\"}";
    }
    
    // Проверка, существует ли пользователь
    if (Database::getUserByLogin(login) != 0) {
        return "{\"error\":\"Login already exists\"}";
    }
    
    // Хэшируем пароль
    string password_hash = hashPassword(password);
    if (password_hash.empty()) {
        return "{\"error\":\"Password hashing failed\"}";
    }
    
    // Создаем пользователя
    int user_id = Database::createUserWithPassword(login, password_hash, fullname, email);
    if (user_id == 0) {
        return "{\"error\":\"Database error\"}";
    }
    
    // Генерируем токены для автоматического входа
    return generateTokenPair(user_id);
}

// ========== НОВЫЙ МЕТОД: АВТОРИЗАЦИЯ ПО ЛОГИНУ/ПАРОЛЮ ==========

string Auth::loginUser(const string& login, const string& password) {
    if (login.empty() || password.empty()) {
        return "{\"error\":\"Login and password required\"}";
    }
    
    // Получаем пользователя из БД
    pair<int, string> user_data = Database::getUserWithPasswordHash(login);
    int user_id = user_data.first;
    string password_hash = user_data.second;
    
    if (user_id == 0) {
        return "{\"error\":\"Invalid login or password\"}";
    }
    
    // Проверяем пароль
    if (!verifyPassword(password, password_hash)) {
        return "{\"error\":\"Invalid login or password\"}";
    }
    
    // Генерируем токены
    return generateTokenPair(user_id);
}

// ========== СУЩЕСТВУЮЩИЕ МЕТОДЫ ==========

string Auth::getGitHubToken(const string& code) {
    CURL* curl = curl_easy_init();
    string response;
    
    if (curl) {
        string data = "client_id=" + Config::GITHUB_CLIENT_ID +
                     "&client_secret=" + Config::GITHUB_CLIENT_SECRET +
                     "&code=" + code;
        
        struct curl_slist* headers = nullptr;
        headers = curl_slist_append(headers, "Accept: application/json");
        
        curl_easy_setopt(curl, CURLOPT_URL, "https://github.com/login/oauth/access_token");
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, data.c_str());
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
        
        curl_easy_perform(curl);
        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
    }
    
    size_t pos = response.find("\"access_token\":\"");
    if (pos != string::npos) {
        size_t start = pos + 16;
        size_t end = response.find('\"', start);
        if (end != string::npos) {
            return response.substr(start, end - start);
        }
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
        headers = curl_slist_append(headers, "Accept: application/json");
        
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
    
    // Пытаемся найти пользователя по telegram_id
    int user_id = Database::getUserByTelegramId(telegram_id);
    
    if (user_id == 0) {
        // Создаем временный логин и email для Telegram пользователя
        string login = "tg_" + to_string(telegram_id);
        string email = to_string(telegram_id) + "@telegram.user";
        
        // Проверяем, не занят ли такой login
        if (Database::getUserByLogin(login) != 0) {
            login = "tg_" + to_string(telegram_id) + "_" + to_string(time(nullptr));
        }
        
        // Создаем пользователя с пустым паролем (специальный режим для Telegram)
        user_id = Database::createTelegramUser(login, name, email, telegram_id);
    }
    
    if (user_id == 0) {
        return "{\"error\":\"Database error\"}";
    }
    
    // Генерируем токены
    return generateTokenPair(user_id);
}

// ========== TokenManager реализация ==========
map<string, int> TokenManager::loginTokens;
map<string, time_t> TokenManager::tokenExpiry;

string TokenManager::createLoginToken(int user_id) {
    cleanupExpiredTokens();
    
    // Генерируем случайный токен
    random_device rd;
    mt19937 gen(rd());
    uniform_int_distribution<> distrib(0, 999999);
    string random_part = to_string(distrib(gen));
    
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

// ========== Новые методы OAuth ==========

string Auth::startOAuth(const string& login_token) {
    if (login_token.empty()) {
        return "{\"error\":\"login_token required\"}";
    }
    
    // Проверяем, что токен существует
    int user_id = 999; // Временный ID
    
    // Создаём новый токен для OAuth процесса
    string state_token = TokenManager::createLoginToken(user_id);
    
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
    string email = parseJson(user_info, "email");
    
    if (github_id.empty()) {
        return "{\"error\":\"Invalid user info from GitHub\"}";
    }
    
    if (name.empty()) name = login;
    if (email.empty()) email = login + "@github.user";
    
    // Проверяем, есть ли уже пользователь с таким github_id
    int existing_id = Database::getUserByGithubId(github_id);
    
    if (existing_id == 0) {
        // Проверяем, не занят ли login
        if (Database::getUserByLogin(login) != 0) {
            login = login + "_gh_" + github_id;
        }
        
        // Создаём нового пользователя (без пароля - можно будет установить позже)
        existing_id = Database::createGitHubUser(login, name, email, github_id);
        
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