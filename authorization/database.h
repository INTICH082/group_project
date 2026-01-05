#pragma once
#include <string>
using namespace std;

class Database {
public:
    static bool connect();
    static void close();
    
    static int getUserByGithubId(const string& github_id);
    static int getUserByTelegramId(long long telegram_id);
    static int createUser(const string& name, 
                         const string& email,
                         const string& github_id = "",
                         long long telegram_id = 0);
};