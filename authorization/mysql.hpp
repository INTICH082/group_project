#pragma once

#include <mysql.h>
#include <string>
#include <vector>
#include <map>

using namespace std;

class MySQLDB {
private:
    MYSQL* conn;

public:
    MySQLDB(const string& host, const string& user, const string& password, const string& db, unsigned int port = 3306);
    ~MySQLDB();

    bool execute(const string& query);
    vector<map<string, string>> fetch_all(const string& query);
};