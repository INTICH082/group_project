#include "database.h"
#include <iostream>

using namespace std;

Database::Database() = default;

bool Database::connect(const string& dbPassword) {
    try {
        driver = sql::mysql::get_mysql_driver_instance();
        con.reset(driver->connect("tcp://127.0.0.1:3306", "root", dbPassword));
        con->setSchema("Project");
        return true;
    } catch (sql::SQLException& e) {
        cerr << "Ошибка подключения к БД: " << e.what() << endl;
        return false;
    }
}

Database::~Database() {
    if (con) con->close();
}

optional<UserInfo> Database::getUserByLogin(const string& login) {
    try {
        unique_ptr<sql::PreparedStatement> pstmt(con->prepareStatement(
            "SELECT ID, User_fullname, User_role, Is_blocked FROM Users WHERE User_login = ?"));
        pstmt->setString(1, login);
        unique_ptr<sql::ResultSet> res(pstmt->executeQuery());

        if (res->next()) {
            UserInfo user;
            user.id = res->getInt("ID");
            user.fullname = res->getString("User_fullname");
            user.login = login;
            user.role = res->getString("User_role");
            user.is_blocked = res->getBoolean("Is_blocked");
            return user;
        }
    } catch (sql::SQLException& e) {
        cerr << "Ошибка запроса к БД: " << e.what() << endl;
    }
    return nullopt;
}

int Database::createUser(const string& login, const string& fullname, const string& role) {
    try {
        unique_ptr<sql::PreparedStatement> pstmt(con->prepareStatement(
            "INSERT INTO Users (User_login, User_fullname, User_role, Is_blocked, Exist) "
            "VALUES (?, ?, ?, 0, 1)"));
        pstmt->setString(1, login);
        pstmt->setString(2, fullname);
        pstmt->setString(3, role);
        pstmt->execute();

        unique_ptr<sql::Statement> stmt(con->createStatement());
        unique_ptr<sql::ResultSet> res(stmt->executeQuery("SELECT LAST_INSERT_ID()"));
        if (res->next()) {
            return res->getInt(1);
        }
    } catch (sql::SQLException& e) {
        cerr << "Ошибка создания пользователя: " << e.what() << endl;
    }
    return -1;
}