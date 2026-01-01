#pragma once

#include "auth.h"
#include <mysql.h>
#include <string>
#include <optional>
#include <stdexcept>

using namespace std;

class Database {
public:
    Database(const string& host, const string& user, const string& pass, const string& dbname);
    ~Database();

    // nullopt если пользователь не найден или ошибка
    optional<UserInfo> getUser(const string& login);

    // true при успехе, false + сообщение в cerr
    bool updateUser(const UserInfo& user);

private:
    MYSQL* conn = nullptr;

    void throwIfError(const string& context) const;
};