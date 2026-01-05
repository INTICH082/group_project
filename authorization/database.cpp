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

int Database::getUserByGithubId(const string& github_id) {
    if (!conn) return 0;
    
    string sql = "SELECT id FROM Users WHERE github_id = '" + github_id + "'";
    
    if (mysql_query(conn, sql.c_str())) {
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
    
    string sql = "SELECT id FROM Users WHERE telegram_id = " + to_string(telegram_id);
    
    if (mysql_query(conn, sql.c_str())) {
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

int Database::createUser(const string& name,
                        const string& email,
                        const string& github_id,
                        long long telegram_id) {
    if (!conn) return 0;
    
    string sql = "INSERT INTO Users (fullname, email, course, role";
    string values = " VALUES ('" + name + "', '" + email + "', 1, 'student'";
    
    if (!github_id.empty()) {
        sql += ", github_id";
        values += ", '" + github_id + "'";
    }
    
    if (telegram_id != 0) {
        sql += ", telegram_id";
        values += ", " + to_string(telegram_id);
    }
    
    sql += ")" + values + ")";
    
    if (mysql_query(conn, sql.c_str())) {
        cerr << "Ошибка SQL: " << mysql_error(conn) << endl;
        return 0;
    }
    
    return mysql_insert_id(conn);
}