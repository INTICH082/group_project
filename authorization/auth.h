#pragma once
#include <string>
#include <map>
using namespace std;

class TokenManager {
private:
    static map<string, int> loginTokens;
    static map<string, time_t> tokenExpiry;
    
public:
    static string createLoginToken(int user_id);
    static int validateLoginToken(const string& token);
    static void cleanupExpiredTokens();
};

class Auth {
public:
    static bool init();
    static void cleanup();
    
    // Основные API методы
    static string startOAuth(const string& login_token);
    static string handleGitHubCallback(const string& code, const string& state);
    static string refreshToken(const string& refresh_token);
    static string verifyToken(const string& token);
    static string telegramAuth(const string& telegram_id_str, const string& name);
    
    // НОВЫЕ МЕТОДЫ: авторизация по логину/паролю
    static string loginUser(const string& login, const string& password);
    static string registerUser(const string& login, const string& password, 
                              const string& fullname, const string& email);
    
    // Вспомогательные методы
    static string generateTokenPair(int user_id);
    static bool parseToken(const string& token, int& user_id, string& type, time_t& created_at);
    static string getGitHubToken(const string& code);
    static string getGitHubUser(const string& token);
    static string parseJson(const string& json, const string& key);
    
    // Методы для работы с паролями
    static string hashPassword(const string& password);
    static bool verifyPassword(const string& password, const string& hash);
    
private:
    static string createToken(const string& data, int expire_seconds);
};