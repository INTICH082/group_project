#include "auth.h"
#include "config.h"
#include "utils.h"
#include "database.h"
#include <ctime>
#include <sstream>
#include <vector>

using namespace std;

string Auth::createToken(int user_id, const string& email, const string& role) {
    ostringstream payload;
    payload << user_id << "|" << email << "|" << role << "|" 
            << (time(nullptr) + Config::JWT_EXPIRE);
    
    string data = payload.str();
    string signature = Utils::sha256(data + Config::JWT_SECRET);
    
    return Utils::base64_encode(data) + "." + signature.substr(0, 32);
}

bool Auth::parseToken(const string& token, int& user_id, string& email, string& role) {
    size_t dot = token.find('.');
    if (dot == string::npos) return false;
    
    string data_b64 = token.substr(0, dot);
    string signature = token.substr(dot + 1);
    
    string data = Utils::base64_decode(data_b64);
    
    // Проверка подписи
    string check_sig = Utils::sha256(data + Config::JWT_SECRET).substr(0, 32);
    if (check_sig != signature) return false;
    
    // Парсинг данных
    vector<string> parts;
    stringstream ss(data);
    string part;
    
    while (getline(ss, part, '|')) {
        parts.push_back(part);
    }
    
    if (parts.size() != 4) return false;
    
    // Проверка времени
    long long exp_time = stoll(parts[3]);
    if (exp_time < time(nullptr)) return false;
    
    user_id = stoi(parts[0]);
    email = parts[1];
    role = parts[2];
    
    return true;
}

bool Auth::validateToken(const string& token, int& user_id, string& email, string& role) {
    return parseToken(token, user_id, email, role);
}

string Auth::registerUser(const string& fullname, const string& email,
                         int course, const string& password, const string& role) {
    Database db;
    if (!db.connect()) return R"({"error":"DB connection failed"})";
    
    // Проверка email
    if (db.getUserId("email", email) > 0) {
        return R"({"error":"Email already exists"})";
    }
    
    // Хэширование пароля
    string hashed_pw = Utils::sha256(password);
    
    // Создание пользователя
    string query = "INSERT INTO Users (fullname, email, course, role, password) VALUES ('" +
                  fullname + "', '" + email + "', " + to_string(course) + 
                  ", '" + role + "', '" + hashed_pw + "')";
    
    int user_id = db.createUser(query);
    if (user_id == 0) return R"({"error":"Registration failed"})";
    
    string token = createToken(user_id, email, role);
    
    return R"({"token":")" + token + R"(","user_id":)" + to_string(user_id) + "}";
}

string Auth::login(const string& email, const string& password) {
    Database db;
    if (!db.connect()) return R"({"error":"DB connection failed"})";
    
    // Получение пользователя
    string query = "SELECT id, password, role FROM Users WHERE email = '" + email + "'";
    if (!db.execute(query)) return R"({"error":"User not found"})";
    
    // Получаем данные (упрощенно)
    query = "SELECT id, password, role FROM Users WHERE email = '" + email + "'";
    string result = db.getSingleValue("SELECT CONCAT(id, '|', password, '|', role) FROM Users WHERE email = '" + email + "'");
    
    if (result.empty()) return R"({"error":"Invalid credentials"})";
    
    // Парсим результат
    size_t pos1 = result.find('|');
    size_t pos2 = result.find('|', pos1 + 1);
    
    if (pos1 == string::npos || pos2 == string::npos) {
        return R"({"error":"Invalid data"})";
    }
    
    string id_str = result.substr(0, pos1);
    string stored_hash = result.substr(pos1 + 1, pos2 - pos1 - 1);
    string role = result.substr(pos2 + 1);
    
    // Проверка пароля
    string input_hash = Utils::sha256(password);
    if (input_hash != stored_hash) return R"({"error":"Invalid password"})";
    
    int user_id = stoi(id_str);
    string token = createToken(user_id, email, role);
    
    return R"({"token":")" + token + R"(","user_id":)" + id_str + R"(,"role":")" + role + "\"}";
}

// Шаблон для OAuth авторизации
template<typename T>
string oauthAuth(const string& provider, T provider_id, const string& name) {
    Database db;
    if (!db.connect()) return R"({"error":"DB connection failed"})";
    
    string field = provider + "_id";
    string id_str = to_string(provider_id);
    
    // Проверка существующего пользователя
    int user_id = db.getUserId(field, id_str);
    
    if (user_id > 0) {
        // Получаем email и роль
        string query = "SELECT email, role FROM Users WHERE " + field + " = '" + id_str + "'";
        string result = db.getSingleValue(query);
        
        if (result.empty()) return R"({"error":"User data not found"})";
        
        size_t pos = result.find('|');
        string email = result.substr(0, pos);
        string role = result.substr(pos + 1);
        
        string token = createToken(user_id, email, role);
        return R"({"token":")" + token + R"(","user_id":)" + to_string(user_id) + "}";
    }
    
    // Создание нового пользователя
    string email = provider + "_" + id_str + "@" + provider + ".user";
    string query = "INSERT INTO Users (fullname, email, course, role, " + field + 
                  ") VALUES ('" + name + "', '" + email + "', 0, 'student', '" + id_str + "')";
    
    user_id = db.createUser(query);
    if (user_id == 0) return R"({"error":"Registration failed"})";
    
    string token = createToken(user_id, email, "student");
    return R"({"token":")" + token + R"(","user_id":)" + to_string(user_id) + "}";
}

string Auth::telegramAuth(long long telegram_id, const string& first_name, const string& last_name) {
    string name = first_name + " " + last_name;
    return oauthAuth<long long>("telegram", telegram_id, name);
}

string Auth::githubAuth(const string& github_id, const string& name) {
    return oauthAuth<string>("github", github_id, name);
}

string Auth::yandexAuth(const string& yandex_id, const string& name) {
    return oauthAuth<string>("yandex", yandex_id, name);
}