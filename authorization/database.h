#pragma once

#include "auth.h"
#include <mysql.h>
#include <string>
#include <optional>

using namespace std;

class Database {
public:
    Database(const string& host, const string& user, const string& pass, const string& dbname);
    ~Database();

    optional<UserInfo> getUser(const string& login);
    int createUser(const string& login, const string& fullname, const string& role = "student");
    bool updateUser(const UserInfo& user);

    void throwIfError(const string& context) const;

private:
    MYSQL* conn = nullptr;
};