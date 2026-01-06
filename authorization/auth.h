#pragma once
#include <string>
#include <map>

using namespace std;

class TokenManager {
private:
    static map<string, int> loginTokens;
public:
    static string createLoginToken(int user_id);
    static int validateLoginToken(const string& token);
    static void cleanupExpiredTokens();
};

class Auth {
public:
    static bool init();
    static void cleanup();
    
    static string startOAuth(const string& login_token);
    static string handleGitHubCallback(const string& code, const string& state);
    static string refreshToken(const string& refresh_token);
    static string verifyToken(const string& token);
    static string telegramAuth(const string& telegram_id_str, const string& name);
    static string loginUser(const string& login, const string& password);
    static string registerUser(const string& login, const string& password, 
                              const string& fullname, const string& email);
    
    static string generateTokenPair(int user_id);
    static bool parseToken(const string& token, int& user_id, string& type, time_t& created_at);

    static string hashPassword(const string& password);
    static bool verifyPassword(const string& password, const string& hash);
    static string getGitHubToken(const string& code);
    static string getGitHubUser(const string& token);
    static string parseJson(const string& json, const string& key);
    
private:
    static string createToken(const string& data, int expire_seconds);
};