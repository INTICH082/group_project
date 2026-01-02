#define _HAS_STD_BYTE 0
#define byte win_byte
#include <windows.h>
#undef byte

#include "database.h"
#include <iostream>
#include <sstream>

using namespace std;

Database::Database(const string& host, const string& user, const string& pass, const string& dbname) {
    conn = mysql_init(nullptr);
    if (!conn) {
        throw runtime_error("mysql_init failed");
    }

    if (!mysql_real_connect(conn, host.c_str(), user.c_str(), pass.c_str(),
                            dbname.c_str(), 3306, nullptr, 0)) {
        string err = mysql_error(conn);
        mysql_close(conn);
        conn = nullptr;
        throw runtime_error("mysql_real_connect failed: " + err);
    }

    mysql_set_character_set(conn, "utf8mb4");
}

Database::~Database() {
    if (conn) {
        mysql_close(conn);
    }
}

void Database::throwIfError(const string& context) const {
    if (mysql_errno(conn) != 0) {
        throw runtime_error(context + ": " + mysql_error(conn));
    }
}

optional<UserInfo> Database::getUser(const string& login) {
    if (!conn) {
        cerr << "Database not connected\n";
        return nullopt;
    }

    string query = "SELECT id, fullname, login, role, is_blocked "
                   "FROM users WHERE login = ? LIMIT 1";

    MYSQL_STMT* stmt = mysql_stmt_init(conn);
    if (!stmt) {
        cerr << "mysql_stmt_init failed\n";
        return nullopt;
    }

    if (mysql_stmt_prepare(stmt, query.c_str(), query.size())) {
        cerr << "mysql_stmt_prepare failed: " << mysql_stmt_error(stmt) << "\n";
        mysql_stmt_close(stmt);
        return nullopt;
    }

    MYSQL_BIND bind[1] = {};
    bind[0].buffer_type = MYSQL_TYPE_STRING;
    bind[0].buffer = const_cast<char*>(login.c_str());
    bind[0].buffer_length = login.size();

    if (mysql_stmt_bind_param(stmt, bind)) {
        cerr << "mysql_stmt_bind_param failed: " << mysql_stmt_error(stmt) << "\n";
        mysql_stmt_close(stmt);
        return nullopt;
    }

    if (mysql_stmt_execute(stmt)) {
        cerr << "mysql_stmt_execute failed: " << mysql_stmt_error(stmt) << "\n";
        mysql_stmt_close(stmt);
        return nullopt;
    }

    MYSQL_BIND result[5] = {};
    int id;
    char fullname[256]{};
    char loginBuf[256]{};
    char role[64]{};
    char isBlocked[2]{};

    unsigned long lengths[5]{};

    result[0].buffer_type = MYSQL_TYPE_LONG;
    result[0].buffer = &id;

    result[1].buffer_type = MYSQL_TYPE_STRING;
    result[1].buffer = fullname;
    result[1].buffer_length = sizeof(fullname);
    result[1].length = &lengths[1];

    result[2].buffer_type = MYSQL_TYPE_STRING;
    result[2].buffer = loginBuf;
    result[2].buffer_length = sizeof(loginBuf);
    result[2].length = &lengths[2];

    result[3].buffer_type = MYSQL_TYPE_STRING;
    result[3].buffer = role;
    result[3].buffer_length = sizeof(role);
    result[3].length = &lengths[3];

    result[4].buffer_type = MYSQL_TYPE_TINY;
    result[4].buffer = isBlocked;
    result[4].buffer_length = sizeof(isBlocked);
    result[4].length = &lengths[4];

    if (mysql_stmt_bind_result(stmt, result)) {
        cerr << "mysql_stmt_bind_result failed: " << mysql_stmt_error(stmt) << "\n";
        mysql_stmt_close(stmt);
        return nullopt;
    }

    if (mysql_stmt_fetch(stmt) == 0) {
        UserInfo user;
        user.id = id;
        user.fullname = string(fullname, lengths[1]);
        user.login = string(loginBuf, lengths[2]);
        user.role = string(role, lengths[3]);
        user.is_blocked = (isBlocked[0] == '1');

        mysql_stmt_close(stmt);
        return user;
    }

    mysql_stmt_close(stmt);
    return nullopt;
}

int Database::createUser(const string& login, const string& fullname, const string& role) {
    if (!conn) {
        cerr << "Database not connected\n";
        return -1;
    }

    string query = "INSERT INTO users (login, fullname, role, is_blocked) VALUES (?, ?, ?, 0)";

    MYSQL_STMT* stmt = mysql_stmt_init(conn);
    if (!stmt) return -1;

    if (mysql_stmt_prepare(stmt, query.c_str(), query.size())) {
        cerr << "prepare failed: " << mysql_stmt_error(stmt) << "\n";
        mysql_stmt_close(stmt);
        return -1;
    }

    MYSQL_BIND bind[3] = {};
    bind[0].buffer_type = MYSQL_TYPE_STRING;
    bind[0].buffer = const_cast<char*>(login.c_str());
    bind[0].buffer_length = login.size();

    bind[1].buffer_type = MYSQL_TYPE_STRING;
    bind[1].buffer = const_cast<char*>(fullname.c_str());
    bind[1].buffer_length = fullname.size();

    bind[2].buffer_type = MYSQL_TYPE_STRING;
    bind[2].buffer = const_cast<char*>(role.c_str());
    bind[2].buffer_length = role.size();

    if (mysql_stmt_bind_param(stmt, bind)) {
        cerr << "bind_param failed: " << mysql_stmt_error(stmt) << "\n";
        mysql_stmt_close(stmt);
        return -1;
    }

    if (mysql_stmt_execute(stmt)) {
        cerr << "execute failed: " << mysql_stmt_error(stmt) << "\n";
        mysql_stmt_close(stmt);
        return -1;
    }

    int new_id = static_cast<int>(mysql_stmt_insert_id(stmt));
    mysql_stmt_close(stmt);
    return new_id;
}

bool Database::updateUser(const UserInfo& user) {
    if (!conn) {
        cerr << "Database not connected\n";
        return false;
    }

    string query = "UPDATE users SET fullname = ?, role = ?, is_blocked = ? "
                   "WHERE id = ?";

    MYSQL_STMT* stmt = mysql_stmt_init(conn);
    if (!stmt) return false;

    if (mysql_stmt_prepare(stmt, query.c_str(), query.size())) {
        cerr << "prepare failed: " << mysql_stmt_error(stmt) << "\n";
        mysql_stmt_close(stmt);
        return false;
    }

    MYSQL_BIND bind[4] = {};
    bind[0].buffer_type = MYSQL_TYPE_STRING;
    bind[0].buffer = const_cast<char*>(user.fullname.c_str());
    bind[0].buffer_length = user.fullname.size();

    bind[1].buffer_type = MYSQL_TYPE_STRING;
    bind[1].buffer = const_cast<char*>(user.role.c_str());
    bind[1].buffer_length = user.role.size();

    char is_blocked_char = user.is_blocked ? 1 : 0;
    bind[2].buffer_type = MYSQL_TYPE_TINY;
    bind[2].buffer = &is_blocked_char;
    bind[2].buffer_length = 1;

    bind[3].buffer_type = MYSQL_TYPE_LONG;
    bind[3].buffer = const_cast<int*>(&user.id);

    if (mysql_stmt_bind_param(stmt, bind)) {
        cerr << "bind_param failed: " << mysql_stmt_error(stmt) << "\n";
        mysql_stmt_close(stmt);
        return false;
    }

    if (mysql_stmt_execute(stmt)) {
        cerr << "execute failed: " << mysql_stmt_error(stmt) << "\n";
        mysql_stmt_close(stmt);
        return false;
    }

    mysql_stmt_close(stmt);
    return true;
}