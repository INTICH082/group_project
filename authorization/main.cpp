#include "crow_all.h"
#include "auth.h"
#include "database.h"
#include "utils.h"

#include <iostream>
#include <string>
#include <map>
#include <cstdlib>      // getenv
#include <exception>
#include <nlohmann/json.hpp>  // если используешь nlohmann/json для парсинга

using namespace std;
using json = nlohmann::json;

int main()
{
    crow::SimpleApp app;

    try
    {
        // Получаем конфигурацию из переменных окружения
        const char* github_client_id     = getenv("GITHUB_CLIENT_ID");
        const char* github_client_secret = getenv("GITHUB_CLIENT_SECRET");
        const char* db_password          = getenv("DB_PASSWORD");
        const char* jwt_secret           = getenv("JWT_SECRET");

        if (!github_client_id || !github_client_secret)
        {
            cerr << "Ошибка: не заданы GITHUB_CLIENT_ID или GITHUB_CLIENT_SECRET\n";
            return 1;
        }

        if (!db_password)
        {
            cerr << "Ошибка: не задана переменная DB_PASSWORD\n";
            return 1;
        }

        if (!jwt_secret || strlen(jwt_secret) < 32)
        {
            cerr << "Ошибка: JWT_SECRET должен быть минимум 32 символа\n";
            return 1;
        }

        // Подключение к базе данных
        Database db("127.0.0.1", "root", db_password, "Project");

        AuthService auth(jwt_secret);  // передаём секрет для JWT

        // 1. Перенаправление на GitHub для авторизации
        CROW_ROUTE(app, "/auth/github")
        ([github_client_id]()
         {
             string url = "https://github.com/login/oauth/authorize"
                          "?client_id=" + string(github_client_id) +
                          "&scope=user:email";
             crow::response res(302);
             res.set_header("Location", url);
             return res;
         });

        // 2. Callback после авторизации GitHub
        CROW_ROUTE(app, "/auth/github/callback")
        ([&db, &auth, github_client_id, github_client_secret](const crow::request& req)
         {
             auto code = req.url_params.get("code");
             if (!code)
             {
                 return crow::response(400, "Параметр code не передан");
             }

             // Получаем access_token
             string token_body = "client_id=" + string(github_client_id) +
                                 "&client_secret=" + string(github_client_secret) +
                                 "&code=" + code;

             map<string, string> headers = {
                 {"Accept", "application/json"}
             };

             string token_response = httpPost("https://github.com/login/oauth/access_token", token_body, headers);

             if (token_response.empty())
             {
                 return crow::response(500, "Не удалось получить токен от GitHub");
             }

             // Парсим JSON-ответ
             json token_json;
             try
             {
                 token_json = json::parse(token_response);
             }
             catch (const json::parse_error& e)
             {
                 cerr << "Ошибка парсинга token_response: " << e.what() << endl;
                 return crow::response(500, "Ошибка обработки ответа GitHub");
             }

             if (!token_json.contains("access_token"))
             {
                 return crow::response(401, "Не получен access_token");
             }

             string access_token = token_json["access_token"];

             // 3. Получаем данные пользователя GitHub
             headers = {
                 {"Authorization", "token " + access_token},
                 {"Accept", "application/vnd.github.v3+json"}
             };

             string user_response = httpGet("https://api.github.com/user", headers);

             if (user_response.empty())
             {
                 return crow::response(500, "Не удалось получить данные пользователя");
             }

             json user_json;
             try
             {
                 user_json = json::parse(user_response);
             }
             catch (const json::parse_error& e)
             {
                 cerr << "Ошибка парсинга user_response: " << e.what() << endl;
                 return crow::response(500, "Ошибка обработки данных пользователя");
             }

             string login = user_json.value("login", "");
             string name  = user_json.value("name", login);

             if (login.empty())
             {
                 return crow::response(500, "Не удалось получить login пользователя");
             }

             // 4. Проверяем / создаём пользователя в БД
             auto user_opt = db.getUser(login);
             UserInfo user;

             if (user_opt)
             {
                 user = *user_opt;
             }
             else
             {
                 // Создаём нового пользователя
                 user.id = db.createUser(login, name, "student");  // роль по умолчанию
                 if (user.id <= 0)
                 {
                     return crow::response(500, "Ошибка создания пользователя в БД");
                 }
                 user.login = login;
                 user.fullname = name;
                 user.role = "student";
                 user.is_blocked = false;
             }

             if (user.is_blocked)
             {
                 return crow::response(403, "Пользователь заблокирован");
             }

             // 5. Генерируем JWT
             string jwt_token = auth.generateToken(user);

             // 6. Возвращаем результат
             json result;
             result["token"]    = jwt_token;
             result["user"]     = {{"login", user.login},
                                   {"fullname", user.fullname},
                                   {"role", user.role}};
             result["message"]  = "Авторизация успешна";

             crow::response res(result);
             res.code = 200;
             return res;
         });

        // 7. Защищённый маршрут — проверка токена
        CROW_ROUTE(app, "/validate")
        ([&auth](const crow::request& req)
         {
             auto auth_header = req.get_header_value("Authorization");
             if (auth_header.empty() || auth_header.find("Bearer ") != 0)
             {
                 return crow::response(401, "Требуется Bearer-токен в заголовке Authorization");
             }

             string token = auth_header.substr(7);

             auto user_opt = auth.validateToken(token);
             if (!user_opt)
             {
                 return crow::response(401, "Недействительный или просроченный токен");
             }

             UserInfo user = *user_opt;

             json result;
             result["valid"]    = true;
             result["user"]     = {{"id", user.id},
                                   {"login", user.login},
                                   {"fullname", user.fullname},
                                   {"role", user.role},
                                   {"blocked", user.is_blocked}};

             return crow::response(result);
         });

        cout << "Сервер запущен на http://localhost:8081\n";
        app.port(8081).multithreaded().run();
    }
    catch (const exception& e)
    {
        cerr << "Критическая ошибка сервера: " << e.what() << endl;
        return 1;
    }
    catch (...)
    {
        cerr << "Неизвестная ошибка\n";
        return 1;
    }

    return 0;
}