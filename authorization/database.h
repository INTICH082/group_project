#pragma once
#include <string>

using namespace std;

class Database {
public:
    static bool connect();
    static void close();
    
    static int getUserByLogin(const string& login);
    static int getUserByGithubId(const string& github_id);
    static int getUserByTelegramId(long long telegram_id);
    
    static pair<int, string> getUserWithPasswordHash(const string& login);
    
    static int createUserWithPassword(const string& login, const string& password_hash,
                                     const string& name, const string& email);
    static int createGitHubUser(const string& login, const string& name,
                               const string& email, const string& github_id);
    static int createTelegramUser(const string& login, const string& name,
                                 const string& email, long long telegram_id);
    
    static bool userExists(int user_id);
};