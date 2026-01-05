#pragma once
#include <string>
#include <utility>
using namespace std;

class Database {
public:
    static bool connect();
    static void close();
    
    // Основные методы поиска
    static int getUserByLogin(const string& login);
    static int getUserByGithubId(const string& github_id);
    static int getUserByTelegramId(long long telegram_id);
    
    // Метод для авторизации по логину/паролю
    static pair<int, string> getUserWithPasswordHash(const string& login);
    
    // Методы создания пользователей
    static int createUserWithPassword(const string& login, const string& password_hash,
                                     const string& name, const string& email);
    static int createGitHubUser(const string& login, const string& name,
                               const string& email, const string& github_id);
    static int createTelegramUser(const string& login, const string& name,
                                 const string& email, long long telegram_id);
    
    // Обновление профиля
    static bool updateUserProfile(int user_id, const string& fullname,
                                 const string& email, const string& password_hash = "");
    
    // Проверка существования
    static bool userExists(int user_id);
};