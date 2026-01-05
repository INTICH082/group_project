#include "database.h"
#include "config.h"
#include <iostream>

using namespace std;

Database::Database() : conn(nullptr) {
    conn = mysql_init(nullptr);
}

Database::~Database() {
    if (conn) mysql_close(conn);
}

bool Database::connect() {
    if (!mysql_real_connect(conn, Config::DB_HOST.c_str(), 
                           Config::DB_USER.c_str(), Config::DB_PASS.c_str(),
                           Config::DB_NAME.c_str(), 0, nullptr, 0)) {
        cout << "DB Error: " << mysql_error(conn) << endl;
        return false;
    }
    return true;
}

bool Database::execute(const string& query) {
    return mysql_query(conn, query.c_str()) == 0;
}

string Database::getSingleValue(const string& query) {
    if (!execute(query)) return "";
    
    MYSQL_RES* result = mysql_store_result(conn);
    if (!result) return "";
    
    MYSQL_ROW row = mysql_fetch_row(result);
    string value = row ? row[0] : "";
    
    mysql_free_result(result);
    return value;
}

int Database::getUserId(const string& field, const string& value) {
    string query = "SELECT id FROM Users WHERE " + field + " = '" + value + "'";
    string id_str = getSingleValue(query);
    return id_str.empty() ? 0 : stoi(id_str);
}

int Database::createUser(const string& query) {
    if (!execute(query)) return 0;
    return mysql_insert_id(conn);
}