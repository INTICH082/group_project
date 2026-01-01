#include "database.h"
#include <iostream>
#include <sstream>

using namespace std;

Database::Database() = default;

bool Database::connect(const string& host, const string& user, const string& password, const string& db) {
    conn = mysql_init(nullptr);
    if (!conn) {
        cerr << "mysql_init failed" << endl;
        return false;
    }

    if (!mysql_real_connect(conn, host.c_str(), user.c_str(), password.c_str(), db.c_str(), 3306, nullptr, 0)) {
        cerr << "mysql_real_connect failed: " << mysql_error(conn) << endl;
        mysql_close(conn);
        conn = nullptr;
        return false;
    }

    // Устанавливаем кодировку UTF-8
    mysql_set_character_set(conn, "utf8mb4");
    return true;
}

Database::~Database() {
    if (conn) mysql_close(conn);
}

optional<UserInfo> Database::getUserByLogin(const string& login) {
    if (!conn) return nullopt;

    string query = "SELECT ID, User_fullname, User_role, Is_blocked FROM Users WHERE User_login = '" + login + "'";
    if (mysql_query(conn, query.c_str())) {
        cerr << "mysql_query failed: " << mysql_error(conn) << endl;
        return nullopt;
    }

    MYSQL_RES* res = mysql_store_result(conn);
    if (!res) return nullopt;

    MYSQL_ROW row = mysql_fetch_row(res);
    if (!row) {
        mysql_free_result(res);
        return nullopt;
    }

    UserInfo user;
    user.id = stoi(row[0]);
    user.fullname = row[1] ? row[1] : "";
    user.login = login;
    user.role = row[2] ? row[2] : "student";
    user.is_blocked = row[3] && string(row[3]) == "1";

    mysql_free_result(res);
    return user;
}

int Database::createUser(const string& login, const string& fullname, const string& role) {
    if (!conn) return -1;

    string query = "INSERT INTO Users (User_login, User_fullname, User_role, Is_blocked, Exist) "
                   "VALUES ('" + login + "', '" + fullname + "', '" + role + "', 0, 1)";
    if (mysql_query(conn, query.c_str())) {
        cerr << "createUser failed: " << mysql_error(conn) << endl;
        return -1;
    }

    return static_cast<int>(mysql_insert_id(conn));
}