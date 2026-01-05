#include "mysql.hpp"
#include "config.hpp"
#include <iostream>

MySQLDB::MySQLDB(const string& host, const string& user, const string& password, const string& db, unsigned int port) {
    conn = mysql_init(nullptr);
    if (!conn) {
        cerr << "mysql_init failed" << endl;
        return;
    }

    if (!mysql_real_connect(conn, host.c_str(), user.c_str(), password.c_str(), db.c_str(), port, nullptr, 0)) {
        cerr << "MySQL connection failed: " << mysql_error(conn) << endl;
        conn = nullptr;
    } else {
        cout << "Подключено к MySQL через libmysql" << endl;
    }
}

MySQLDB::~MySQLDB() {
    if (conn) mysql_close(conn);
}

bool MySQLDB::execute(const string& query) {
    return mysql_query(conn, query.c_str()) == 0;
}

vector<map<string, string>> MySQLDB::fetch_all(const string& query) {
    vector<map<string, string>> rows;
    if (mysql_query(conn, query.c_str()) != 0) {
        cerr << "Query failed: " << mysql_error(conn) << endl;
        return rows;
    }

    MYSQL_RES* res = mysql_store_result(conn);
    if (!res) return rows;

    MYSQL_ROW row;
    unsigned int num_fields = mysql_num_fields(res);
    MYSQL_FIELD* fields = mysql_fetch_fields(res);

    while ((row = mysql_fetch_row(res))) {
        map<string, string> r;
        for (unsigned int i = 0; i < num_fields; ++i) {
            r[fields[i].name] = row[i] ? row[i] : "";
        }
        rows.push_back(r);
    }

    mysql_free_result(res);
    return rows;
}