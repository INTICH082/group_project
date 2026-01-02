#include "crow.h"         
#include "auth.h"
#include "database.h"
#include "utils.h"

#include <iostream>
#include <string>
#include <map>
#include <cstdlib>      // getenv
#include <exception>

using namespace std;

int main()
{
    crow::SimpleApp app;

    try
    {
        const char* github_client_id     = getenv("GITHUB_CLIENT_ID");
        const char* github_client_secret = getenv("GITHUB_CLIENT_SECRET");
        const char* db_password          = getenv("DB_PASSWORD");

        if (!github_client_id || !github_client_secret)
        {
            cerr << "Не заданы GITHUB_CLIENT_ID или GITHUB_CLIENT_SECRET\n";
            return 1;
        }

        if (!db_password)
        {
            cerr << "Не задана DB_PASSWORD\n";
            return 1;
        }

        Database db("127.0.0.1", "root", db_password, "Project");

        // Авторизация через GitHub
        CROW_ROUTE(app, "/auth/github")
        ([github_client_id]()
         {
             string url = "https://github.com/login/oauth/authorize?client_id=" + string(github_client_id) + "&scope=user";
             crow::response res(302);
             res.set_header("Location", url);
             return res;
         });

        CROW_ROUTE(app, "/auth/github/callback")
        ([&db](const crow::request& req)
         {
             auto code = req.url_params.get("code");
             if (!code)
             {
                 return crow::response(400, "Параметр code не передан");
             }

             cout << "Получен code: " << code << "\n";

             // Здесь: обмен code на token, получение пользователя, создание в БД, JWT

             return crow::response(200, "Авторизация успешна");
         });

        // Пример защищённого маршрута
        CROW_ROUTE(app, "/validate")
        ([](const crow::request& req)
         {
             auto auth = req.get_header_value("Authorization");
             if (auth.empty() || auth.find("Bearer ") != 0)
             {
                 return crow::response(401, "Требуется Bearer-токен");
             }

             return crow::response(200, "Токен действителен");
         });

        cout << "Сервер запущен на http://localhost:8081\n";
        app.port(8081).multithreaded().run();
    }
    catch (const exception& e)
    {
        cerr << "Ошибка: " << e.what() << endl;
        return 1;
    }

    return 0;
}