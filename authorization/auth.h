#pragma once
#include <string>

using namespace std;

class Auth {
public:
    // Основные методы
    static string registerUser(const string& fullname, const string& email,
                              int course, const string& password, 
                              const string& role = "student");
    
    static string login(const string& email, const string& password);
    
    // OAuth методы
    static string telegramAuth(long long telegram_id, 
                              const string& first_name, const string& last_name);
    
    static string githubAuth(const string& github_id, const string& name);
    
    static string yandexAuth(const string& yandex_id, const string& name);
    
    // Валидация
    static bool validateToken(const string& token, int& user_id, 
                             string& email, string& role);
    
private:
    static string createToken(int user_id, const string& email, const string& role);
    static bool parseToken(const string& token, int& user_id, 
                          string& email, string& role);
};