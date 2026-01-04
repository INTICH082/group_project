#define _HAS_STD_BYTE 0

#include "crow.h"         
#include "auth.h"
#include "database.h"
#include "utils.h"

#include <iostream>
#include <string>
#include <map>
#include <cstdlib>      // getenv
#include <exception>
#include "json.hpp"     // для парсинга JSON от GitHub

using namespace std;
using nlohmann::json;

int main()
{
    cout << "1. Server started main()" << endl;

    try
    {
        const char* github_client_id     = getenv("GITHUB_CLIENT_ID");
        const char* github_client_secret = getenv("GITHUB_CLIENT_SECRET");
        const char* db_password          = getenv("DB_PASSWORD");
        const char* jwt_secret           = getenv("JWT_SECRET");

        cout << "2. Env variables read" << endl;
        cout << "GITHUB_CLIENT_ID: " << (github_client_id ? github_client_id : "NOT SET") << endl;
        cout << "GITHUB_CLIENT_SECRET: " << (github_client_secret ? "SET" : "NOT SET") << endl;  // Не выводи секрет!
        cout << "DB_PASSWORD: " << (db_password ? "SET" : "NOT SET") << endl;  // Не выводи пароль!
        cout << "JWT_SECRET: " << (jwt_secret ? "SET" : "NOT SET") << endl;

        if (!github_client_id || !github_client_secret || !db_password || !jwt_secret) {
            cerr << "Error: Missing environment variables" << endl;
            return 1;
        }

        cout << "3. Creating Database..." << endl;
        Database db("localhost", "root", db_password, "Project");  // Используем env DB_PASSWORD

        cout << "4. Creating AuthService..." << endl;
        AuthService auth(jwt_secret);  // Используем env JWT_SECRET

        cout << "5. Creating Crow app..." << endl;
        crow::SimpleApp app;
        cout << "6. Crow app created" << endl;

        // Тестовый маршрут для проверки
        CROW_ROUTE(app, "/test")([](){
            return "Server is alive! Everything works.";
        });

        // Маршрут для начала OAuth (перенаправление на GitHub)
        CROW_ROUTE(app, "/auth/github")([&](){
            string oauth_url = "https://github.com/login/oauth/authorize?client_id=" + string(github_client_id) + "&redirect_uri=http://localhost:8081/auth/github/callback";
            crow::response res;
            res.code = 302;
            res.add_header("Location", oauth_url);
            return res;
        });

        // Callback-маршрут после GitHub (получаем код, обмениваем на токен, получаем пользователя, генерируем JWT)
        CROW_ROUTE(app, "/auth/github/callback")([&](const crow::request& req){
            auto params = req.url_params;
            string code = params.get("code");

            if (code.empty()) {
                return crow::response(400, "No code provided");
            }

            // Обмен code на access_token через GitHub API
            string token_url = "https://github.com/login/oauth/access_token";
            map<string, string> post_data = {
                {"client_id", github_client_id},
                {"client_secret", github_client_secret},
                {"code", code}
            };
            string token_response = httpPost(token_url, "", post_data);  // Используем utils.cpp

            // Парсим access_token из ответа
            json token_json = json::parse(token_response);
            string access_token = token_json["access_token"];

            if (access_token.empty()) {
                return crow::response(500, "Failed to get access token");
            }

            // Получаем данные пользователя от GitHub
            string user_url = "https://api.github.com/user";
            map<string, string> headers = {{"Authorization", "Bearer " + access_token}};
            string user_response = httpGet(user_url, headers);

            json user_json = json::parse(user_response);

            // Создаём UserInfo из GitHub-данных
            UserInfo user;
            user.login = user_json["login"];
            user.fullname = user_json["name"];
            user.role = "student";  // По умолчанию
            user.is_blocked = false;
            user.id = db.createUser(user.login, user.fullname, user.role);  // Сохраняем в БД

            // Генерируем JWT
            string jwt_token = auth.generateToken(user);

            // Возвращаем токен (или редирект на главную с токеном)
            return crow::response(200, "JWT Token: " + jwt_token);
        });

        // Защищённый маршрут (пример, проверяет токен)
        CROW_ROUTE(app, "/profile")([&](const crow::request& req){
            auto auth_header = req.get_header_value("Authorization");
            if (auth_header.empty() || auth_header.find("Bearer ") != 0) {
                return crow::response(401, "Unauthorized");
            }

            string token = auth_header.substr(7);
            auto user_opt = auth.validateToken(token);
            if (!user_opt) {
                return crow::response(401, "Invalid token");
            }

            return crow::response(200, "Welcome, " + user_opt->fullname);
        });

        cout << "7. Routes registered" << endl;

        cout << "8. Starting server on port 8081..." << endl;
        app.port(8081).multithreaded().run();
        cout << "9. Server stopped (should not reach here)" << endl;
    }
    catch (const exception& e)
    {
        cerr << "Exception in main: " << e.what() << endl;
        return 1;
    }

    cout << "10. main() finished" << endl;
    return 0;
}