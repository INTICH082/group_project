#pragma once
#include <mysql_driver.h>
#include <mysql_connection.h>
#include <cppconn/prepared_statement.h>
#include <cppconn/resultset.h>
#include <memory>
#include <string>
#include <optional>

struct UserInfo {
    int id;
    string fullname;
    string login;     // GitHub username
    string role;
    bool is_blocked;
};

class Database {
public:
    Database();
    ~Database();

    bool connect(const string& dbPassword);

    optional<UserInfo> getUserByLogin(const string& login);

    int createUser(const string& login, const string& fullname, const string& role = "student");

private:
    unique_ptr<sql::mysql::MySQL_Driver> driver;
    unique_ptr<sql::Connection> con;
};