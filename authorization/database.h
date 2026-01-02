#pragma once

#include "auth.h"
#include <mysql.h>
#include <string>
#include <optional>

using namespace std;

class Database {
public:
    Database(const string& host, const string& user, const string& pass, const string& db);
    ~Database();

    optional<UserInfo> getUser(const string& login);
    int createUser(const string& login, const string& fullname, const string& role = "student");

private:
    MYSQL* conn = nullptr;
};