#include <crow.h>
#include <nlohmann/json.hpp>
#include <iostream>
#include "config.hpp"
#include "handlers.hpp"
#include "mysql.hpp"
#include "utils.hpp"

using namespace std;
using json = nlohmann::json;

Config cfg;

MySQLDB db(cfg.mysql_host, cfg.mysql_user, cfg.mysql_password, cfg.mysql_db, cfg.mysql_port);

int main() {
    crow::SimpleApp app;

    // Регистрация: POST /register { fullname, course, role, password }
    CROW_ROUTE(app, "/register").methods("POST"_method)
    ([](const crow::request& req) {
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

            string query = "INSERT INTO users (fullname, course, role, password) VALUES ('" + fullname + "', " + to_string(course) + ", '" + role + "', '" + hash + "')";

            if (db.execute(query)) {
                return crow::response(200, "Пользователь успешно зарегистрирован");
            } else {
                return crow::response(409, "Пользователь с таким fullname уже существует");
            }
        } catch (...) {
            return crow::response(400, "Неверный JSON");
        }
    });

    // Авторизация: POST /login { fullname, password }
    CROW_ROUTE(app, "/login").methods("POST"_method)
    ([](const crow::request& req) {
        try {
            auto body = json::parse(req.body);
            string fullname = body["fullname"];
            string password = body["password"];

            string hash = sha256(password);

            string query = "SELECT id, fullname, course, role FROM users WHERE fullname = '" + fullname + "' AND password = '" + hash + "'";
            auto res = db.fetch_all(query);

            if (!res.empty()) {
                string token = generate_token();

                db.execute("UPDATE users SET token = '" + token + "' WHERE id = " + res[0]["id"]);

                json response;
                response["token"] = token;
                response["fullname"] = res[0]["fullname"];
                response["course"] = stoi(res[0]["course"]);
                response["role"] = res[0]["role"];

                return crow::response(200, response.dump());
            } else {
                return crow::response(401, "Неверное fullname или пароль");
            }
        } catch (...) {
            return crow::response(400, "Неверный запрос");
        }
    });

    // Проверка токена: GET /me?token=...
    CROW_ROUTE(app, "/me").methods("GET"_method)
    ([](const crow::request& req) {
        string token = req.url_params.get("token");
        if (token.empty()) return crow::response(400, "token обязателен");

        string query = "SELECT fullname, course, role FROM users WHERE token = '" + token + "'";
        auto res = db.fetch_all(query);

        if (!res.empty()) {
            json response;
            response["fullname"] = res[0]["fullname"];
            response["course"] = stoi(res[0]["course"]);
            response["role"] = res[0]["role"];
            return crow::response(200, response.dump());
        }
        return crow::response(401, "Неверный токен");
    });

    register_routes(app);

    cout << "Сервер запущен на http://localhost:" << cfg.server_port << endl;
    app.port(cfg.server_port).multithreaded().run();
    return 0;
}