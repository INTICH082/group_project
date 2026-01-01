#pragma once
#include <mysql.h>
#include <string>
#include <optional>

using namespace std;

struct UserInfo {
    int id;
    string fullname;
    string login;
    string role;
    bool is_blocked;
};

class Database {
public:
    Database();
    ~Database();

    bool connect(const string& host = "127.0.0.1",
                 const string& user = "root",
                 const string& password = "",
                 const string& db = "Project");

    optional<UserInfo> getUserByLogin(const string& login);
    int createUser(const string& login, const string& fullname, const string& role = "student");

private:
    MYSQL* conn = nullptr;
};