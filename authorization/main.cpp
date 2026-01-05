#include <crow.h>
#include <mysql_driver.h>
#include <mysql_connection.h>
#include <cppconn/prepared_statement.h>
#include <nlohmann/json.hpp>
#include <iostream>
#include "config.hpp"

using namespace std;
using json = nlohmann::json;

Config cfg;

string sha256(const string&);
string generate_token();

int main() {
    crow::SimpleApp app;

    sql::mysql::MySQL_Driver* driver;
    unique_ptr<sql::Connection> con;

    try {
        driver = sql::mysql::get_mysql_driver_instance();
        con.reset(driver->connect("tcp://" + cfg.mysql_host + ":" + to_string(cfg.mysql_port),
                                  cfg.mysql_user, cfg.mysql_password));
        con->setSchema(cfg.mysql_db);
        cout << "Подключено к MySQL (база: " << cfg.mysql_db << ")" << endl;
    } catch (sql::SQLException& e) {
        cerr << "Ошибка подключения к MySQL: " << e.what() << endl;
        return 1;
    }

    // Регистрация: POST /register
    // JSON: { "fullname", "course", "role", "password" }
    CROW_ROUTE(app, "/register").methods("POST"_method)
    ([&con](const crow::request& req) {
        try {
            auto body = json::parse(req.body);

            string fullname = body["fullname"];
            int course = body["course"];
            string role = body["role"];
            string password = body["password"];

            if (fullname.empty() || password.empty()) {
                return crow::response(400, "fullname и password обязательны");
            }

            string hash = sha256(password);

            unique_ptr<sql::PreparedStatement> pstmt(con->prepareStatement(
                "INSERT INTO users (fullname, course, role, password) VALUES (?, ?, ?, ?)"));
            pstmt->setString(1, fullname);
            pstmt->setInt(2, course);
            pstmt->setString(3, role);
            pstmt->setString(4, hash);
            pstmt->executeUpdate();

            return crow::response(200, "Пользователь успешно зарегистрирован");
        } catch (sql::SQLException& e) {
            if (e.getErrorCode() == 1062) {  // дубликат fullname
                return crow::response(409, "Пользователь с таким fullname уже существует");
            }
            return crow::response(500, "Ошибка базы данных: " + string(e.what()));
        } catch (...) {
            return crow::response(400, "Неверный JSON");
        }
    });

    // Авторизация: POST /login
    // JSON: { "fullname", "password" }
    CROW_ROUTE(app, "/login").methods("POST"_method)
    ([&con](const crow::request& req) {
        try {
            auto body = json::parse(req.body);
            string fullname = body["fullname"];
            string password = body["password"];

            string hash = sha256(password);

            unique_ptr<sql::PreparedStatement> pstmt(con->prepareStatement(
                "SELECT id, fullname, course, role FROM users WHERE fullname = ? AND password = ?"));
            pstmt->setString(1, fullname);
            pstmt->setString(2, hash);

            unique_ptr<sql::ResultSet> res(pstmt->executeQuery());

            if (res->next()) {
                string token = generate_token();

                // Сохраняем токен
                unique_ptr<sql::PreparedStatement> update(con->prepareStatement(
                    "UPDATE users SET token = ? WHERE id = ?"));
                update->setString(1, token);
                update->setInt(2, res->getInt("id"));
                update->executeUpdate();

                json response;
                response["token"] = token;
                response["fullname"] = res->getString("fullname");
                response["course"] = res->getInt("course");
                response["role"] = res->getString("role");

                return crow::response(200, response.dump());
            } else {
                return crow::response(401, "Неверное fullname или пароль");
            }
        } catch (...) {
            return crow::response(400, "Неверный запрос");
        }
    });

    // Проверка текущего пользователя: GET /me?token=...
    CROW_ROUTE(app, "/me")
    ([&con](const crow::request& req) {
        string token = req.url_params.get("token");
        if (token.empty()) {
            return crow::response(400, "Токен обязателен");
        }

        unique_ptr<sql::PreparedStatement> pstmt(con->prepareStatement(
            "SELECT fullname, course, role FROM users WHERE token = ?"));
        pstmt->setString(1, token);
        unique_ptr<sql::ResultSet> res(pstmt->executeQuery());

        if (res->next()) {
            json response;
            response["fullname"] = res->getString("fullname");
            response["course"] = res->getInt("course");
            response["role"] = res->getString("role");
            return crow::response(200, response.dump());
        }
        return crow::response(401, "Неверный или просроченный токен");
    });

    cout << "Сервер запущен на http://localhost:" << cfg.server_port << endl;
    app.port(cfg.server_port).multithreaded().run();
    return 0;
}