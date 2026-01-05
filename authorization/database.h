#pragma once
#include <mysql/mysql.h>
#include <string>

using namespace std;

class Database {
public:
    Database();
    ~Database();
    
    bool connect();
    bool execute(const string& query);
    string getSingleValue(const string& query);
    int getUserId(const string& field, const string& value);
    int createUser(const string& query);
    
private:
    MYSQL* conn;
};