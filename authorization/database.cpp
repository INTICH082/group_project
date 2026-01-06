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

int Database::getUserByLogin(const string& login) {
    if (!conn) return 0;
    
    string sql = "SELECT id FROM users WHERE login = '" + login + "'";
    
    if (mysql_query(conn, sql.c_str())) return 0;
    
    MYSQL_RES* res = mysql_store_result(conn);
    if (!res) return 0;
    
    int user_id = 0;
    MYSQL_ROW row = mysql_fetch_row(res);
    if (row) user_id = atoi(row[0]);
    
    mysql_free_result(res);
    return user_id;
}

pair<int, string> Database::getUserWithPasswordHash(const string& login) {
    pair<int, string> result = {0, ""};
    if (!conn) return result;
    
    string sql = "SELECT id, password FROM users WHERE login = '" + login + "'";
    
    if (mysql_query(conn, sql.c_str())) return result;
    
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

int Database::createUserWithPassword(const string& login, const string& password_hash,
                                    const string& name, const string& email) {
    if (!conn) return 0;
    
    string sql = "INSERT INTO users (login, password, fullname, email) VALUES ('" + 
                login + "', '" + password_hash + "', '" + name + "', '" + email + "')";
    
    if (mysql_query(conn, sql.c_str())) {
        cerr << "Ошибка SQL: " << mysql_error(conn) << endl;
        return 0;
    }
    
    return mysql_insert_id(conn);
}

int Database::createGitHubUser(const string& login, const string& name,
                              const string& email, const string& github_id) {
    if (!conn) return 0;
    
    string sql = "INSERT INTO users (login, password, fullname, email, github_id) VALUES ('" + 
                login + "', '', '" + name + "', '" + email + "', '" + github_id + "')";
    
    if (mysql_query(conn, sql.c_str())) return 0;
    return mysql_insert_id(conn);
}

int Database::createTelegramUser(const string& login, const string& name,
                                const string& email, long long telegram_id) {
    if (!conn) return 0;
    
    string sql = "INSERT INTO users (login, password, fullname, email, telegram_id) VALUES ('" + 
                login + "', '', '" + name + "', '" + email + "', " + to_string(telegram_id) + ")";
    
    if (mysql_query(conn, sql.c_str())) return 0;
    return mysql_insert_id(conn);
}

int Database::getUserByGithubId(const string& github_id) {
    if (!conn) return 0;
    
    string sql = "SELECT id FROM users WHERE github_id = '" + github_id + "'";
    
    if (mysql_query(conn, sql.c_str())) return 0;
    
    MYSQL_RES* res = mysql_store_result(conn);
    if (!res) return 0;
    
    int user_id = 0;
    MYSQL_ROW row = mysql_fetch_row(res);
    if (row) user_id = atoi(row[0]);
    
    mysql_free_result(res);
    return user_id;
}

int Database::getUserByTelegramId(long long telegram_id) {
    if (!conn) return 0;
    
    string sql = "SELECT id FROM users WHERE telegram_id = " + to_string(telegram_id);
    
    if (mysql_query(conn, sql.c_str())) return 0;
    
    MYSQL_RES* res = mysql_store_result(conn);
    if (!res) return 0;
    
    int user_id = 0;
    MYSQL_ROW row = mysql_fetch_row(res);
    if (row) user_id = atoi(row[0]);
    
    mysql_free_result(res);
    return user_id;
}

bool Database::userExists(int user_id) {
    if (!conn) return false;
    
    string sql = "SELECT id FROM users WHERE id = " + to_string(user_id);
    
    if (mysql_query(conn, sql.c_str())) return false;
    
    MYSQL_RES* res = mysql_store_result(conn);
    if (!res) return false;
    
    bool exists = (mysql_fetch_row(res) != nullptr);
    mysql_free_result(res);
    return exists;
}