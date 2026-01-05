#include "database.h"
#include "config.h"
#include <mysql.h>  
#include <iostream>
using namespace std;

static MYSQL* conn = nullptr;

bool Database::connect() {
    if (conn) return true;
    
    conn = mysql_init(nullptr);
    if (!conn) {
        cerr << "Ошибка MySQL init" << endl;
        return false;
    }
    
    if (!mysql_real_connect(conn, 
                           Config::DB_HOST.c_str(),
                           Config::DB_USER.c_str(),
                           Config::DB_PASS.c_str(),
                           Config::DB_NAME.c_str(),
                           0, nullptr, 0)) {
        cerr << "Ошибка подключения: " << mysql_error(conn) << endl;
        return false;
    }
    
    cout << "✅ Подключено к БД" << endl;
    return true;
}

void Database::close() {
    if (conn) {
        mysql_close(conn);
        conn = nullptr;
    }
}

// ========== НОВЫЙ МЕТОД: поиск по логину ==========

int Database::getUserByLogin(const string& login) {
    if (!conn) return 0;
    
    // Используем экранирование для безопасности
    char escaped_login[101];
    mysql_real_escape_string(conn, escaped_login, login.c_str(), login.length());
    
    string sql = "SELECT id FROM users WHERE login = '";
    sql += escaped_login;
    sql += "'";
    
    if (mysql_query(conn, sql.c_str())) {
        cerr << "Ошибка SQL: " << mysql_error(conn) << endl;
        return 0;
    }
    
    MYSQL_RES* res = mysql_store_result(conn);
    if (!res) return 0;
    
    int user_id = 0;
    MYSQL_ROW row = mysql_fetch_row(res);
    if (row) {
        user_id = atoi(row[0]);
    }
    
    mysql_free_result(res);
    return user_id;
}

// ========== НОВЫЙ МЕТОД: получение пароля для проверки ==========

pair<int, string> Database::getUserWithPasswordHash(const string& login) {
    pair<int, string> result = {0, ""};
    if (!conn) return result;
    
    // Экранирование
    char escaped_login[101];
    mysql_real_escape_string(conn, escaped_login, login.c_str(), login.length());
    
    string sql = "SELECT id, password FROM users WHERE login = '";
    sql += escaped_login;
    sql += "'";
    
    if (mysql_query(conn, sql.c_str())) {
        cerr << "Ошибка SQL: " << mysql_error(conn) << endl;
        return result;
    }
    
    MYSQL_RES* res = mysql_store_result(conn);
    if (!res) return result;
    
    MYSQL_ROW row = mysql_fetch_row(res);
    if (row && row[0] && row[1]) {
        result.first = atoi(row[0]);
        result.second = row[1];
    }
    
    mysql_free_result(res);
    return result;
}

// ========== НОВЫЙ МЕТОД: создание пользователя с паролем ==========

int Database::createUserWithPassword(const string& login, const string& password_hash,
                                    const string& name, const string& email) {
    if (!conn) return 0;
    
    // Экранирование всех полей
    char escaped_login[101];
    char escaped_password[256];
    char escaped_name[71];
    char escaped_email[61];
    
    mysql_real_escape_string(conn, escaped_login, login.c_str(), login.length());
    mysql_real_escape_string(conn, escaped_password, password_hash.c_str(), password_hash.length());
    mysql_real_escape_string(conn, escaped_name, name.c_str(), name.length());
    mysql_real_escape_string(conn, escaped_email, email.c_str(), email.length());
    
    string sql = "INSERT INTO users (login, password, fullname, email) VALUES ('";
    sql += escaped_login;
    sql += "', '";
    sql += escaped_password;
    sql += "', '";
    sql += escaped_name;
    sql += "', '";
    sql += escaped_email;
    sql += "')";
    
    if (mysql_query(conn, sql.c_str())) {
        cerr << "Ошибка SQL: " << mysql_error(conn) << endl;
        return 0;
    }
    
    return mysql_insert_id(conn);
}

// ========== НОВЫЙ МЕТОД: создание GitHub пользователя ==========

int Database::createGitHubUser(const string& login, const string& name,
                              const string& email, const string& github_id) {
    if (!conn) return 0;
    
    // Экранирование
    char escaped_login[101];
    char escaped_name[71];
    char escaped_email[61];
    char escaped_github[101];
    
    mysql_real_escape_string(conn, escaped_login, login.c_str(), login.length());
    mysql_real_escape_string(conn, escaped_name, name.c_str(), name.length());
    mysql_real_escape_string(conn, escaped_email, email.c_str(), email.length());
    mysql_real_escape_string(conn, escaped_github, github_id.c_str(), github_id.length());
    
    string sql = "INSERT INTO users (login, password, fullname, email, github_id) VALUES ('";
    sql += escaped_login;
    sql += "', '', '";
    sql += escaped_name;
    sql += "', '";
    sql += escaped_email;
    sql += "', '";
    sql += escaped_github;
    sql += "')";
    
    if (mysql_query(conn, sql.c_str())) {
        cerr << "Ошибка SQL: " << mysql_error(conn) << endl;
        return 0;
    }
    
    return mysql_insert_id(conn);
}

// ========== НОВЫЙ МЕТОД: создание Telegram пользователя ==========

int Database::createTelegramUser(const string& login, const string& name,
                                const string& email, long long telegram_id) {
    if (!conn) return 0;
    
    // Экранирование
    char escaped_login[101];
    char escaped_name[71];
    char escaped_email[61];
    
    mysql_real_escape_string(conn, escaped_login, login.c_str(), login.length());
    mysql_real_escape_string(conn, escaped_name, name.c_str(), name.length());
    mysql_real_escape_string(conn, escaped_email, email.c_str(), email.length());
    
    string sql = "INSERT INTO users (login, password, fullname, email, telegram_id) VALUES ('";
    sql += escaped_login;
    sql += "', '', '";
    sql += escaped_name;
    sql += "', '";
    sql += escaped_email;
    sql += "', ";
    sql += to_string(telegram_id);
    sql += ")";
    
    if (mysql_query(conn, sql.c_str())) {
        cerr << "Ошибка SQL: " << mysql_error(conn) << endl;
        return 0;
    }
    
    return mysql_insert_id(conn);
}

// ========== СУЩЕСТВУЮЩИЕ МЕТОДЫ ==========

int Database::getUserByGithubId(const string& github_id) {
    if (!conn) return 0;
    
    char escaped_github[101];
    mysql_real_escape_string(conn, escaped_github, github_id.c_str(), github_id.length());
    
    string sql = "SELECT id FROM users WHERE github_id = '";
    sql += escaped_github;
    sql += "'";
    
    if (mysql_query(conn, sql.c_str())) {
        cerr << "Ошибка SQL: " << mysql_error(conn) << endl;
        return 0;
    }
    
    MYSQL_RES* res = mysql_store_result(conn);
    if (!res) return 0;
    
    int user_id = 0;
    MYSQL_ROW row = mysql_fetch_row(res);
    if (row) {
        user_id = atoi(row[0]);
    }
    
    mysql_free_result(res);
    return user_id;
}

int Database::getUserByTelegramId(long long telegram_id) {
    if (!conn) return 0;
    
    string sql = "SELECT id FROM users WHERE telegram_id = " + to_string(telegram_id);
    
    if (mysql_query(conn, sql.c_str())) {
        cerr << "Ошибка SQL: " << mysql_error(conn) << endl;
        return 0;
    }
    
    MYSQL_RES* res = mysql_store_result(conn);
    if (!res) return 0;
    
    int user_id = 0;
    MYSQL_ROW row = mysql_fetch_row(res);
    if (row) {
        user_id = atoi(row[0]);
    }
    
    mysql_free_result(res);
    return user_id;
}

// ========== НОВЫЙ МЕТОД: обновление профиля ==========

bool Database::updateUserProfile(int user_id, const string& fullname,
                                const string& email, const string& password_hash) {
    if (!conn) return false;
    
    char escaped_name[71];
    char escaped_email[61];
    char escaped_password[256];
    
    mysql_real_escape_string(conn, escaped_name, fullname.c_str(), fullname.length());
    mysql_real_escape_string(conn, escaped_email, email.c_str(), email.length());
    
    string sql = "UPDATE users SET fullname = '";
    sql += escaped_name;
    sql += "', email = '";
    sql += escaped_email;
    sql += "'";
    
    if (!password_hash.empty()) {
        mysql_real_escape_string(conn, escaped_password, password_hash.c_str(), password_hash.length());
        sql += ", password = '";
        sql += escaped_password;
        sql += "'";
    }
    
    sql += " WHERE id = ";
    sql += to_string(user_id);
    
    if (mysql_query(conn, sql.c_str())) {
        cerr << "Ошибка SQL: " << mysql_error(conn) << endl;
        return false;
    }
    
    return mysql_affected_rows(conn) > 0;
}

bool Database::userExists(int user_id) {
    if (!conn) return false;
    
    string sql = "SELECT id FROM users WHERE id = " + to_string(user_id);
    
    if (mysql_query(conn, sql.c_str())) {
        return false;
    }
    
    MYSQL_RES* res = mysql_store_result(conn);
    if (!res) return false;
    
    bool exists = (mysql_fetch_row(res) != nullptr);
    mysql_free_result(res);
    
    return exists;
}