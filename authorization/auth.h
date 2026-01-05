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
    
    static string homePage();
    
    // Старт OAuth процесса
    static string startOAuth(const string& login_token);
    
    // Обработка callback от GitHub
    static string handleGitHubCallback(const string& code, const string& state);
    
    // Обновление токенов
    static string refreshToken(const string& refresh_token);
    
    // Проверка access token
    static string verifyToken(const string& token);
    
    // Прямая авторизация Telegram (старый метод, оставить для обратной совместимости)
    static string telegramAuth(const string& telegram_id_str, const string& name);
    
    // Генерация пары токенов (для внутреннего использования)
    static string generateTokenPair(int user_id);

    static bool parseToken(const string& token, int& user_id, string& type, time_t& created_at);

    static string getGitHubToken(const string& code);

    static string getGitHubUser(const string& token);

    static string parseJson(const string& json, const string& key);
    
private:
    static string createToken(const string& data, int expire_seconds);
};