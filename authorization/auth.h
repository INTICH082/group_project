#pragma once
#include <string>
using namespace std;

class Auth {
public:
    static bool init();
    static void cleanup();
    
    static string homePage();
    static string githubAuth(const string& code);
    static string telegramAuth(const string& telegram_id_str, const string& name);
    static string verifyToken(const string& token);
};