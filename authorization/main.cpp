#include "crow_all.h"
#include "database.h"
#include "auth.h"
#include "utils.h"
#include "json.hpp"
#include <iostream>
#include <cstdlib>

using namespace std;
using json = nlohmann::json;

string httpGet(const string& url, const map<string, string>& headers = {});
string httpPost(const string& url, const string& body, const map<string, string>& headers = {});

int main() {
    crow::SimpleApp app;
    Database db;
    AuthService auth;

    const char* dbPass = getenv("DB_PASSWORD");
    if (!dbPass || !db.connect(dbPass)) {
        cerr << "Не удалось подключиться к базе данных" << endl;
        return 1;
    }

    const char* clientId = getenv("GITHUB_CLIENT_ID");
    const char* clientSecret = getenv("GITHUB_CLIENT_SECRET");
    if (!clientId || !clientSecret) {
        cerr << "Не заданы GITHUB_CLIENT_ID или GITHUB_CLIENT_SECRET" << endl;
        return 1;
    }
    string githubClientId = clientId;
    string githubClientSecret = clientSecret;

    // Начало OAuth
    CROW_ROUTE(app, "/auth/github")([githubClientId]() {
        string url = "https://github.com/login/oauth/authorize?client_id=" + githubClientId + "&scope=user";
        crow::response res;
        res.code = 302;
        res.set_header("Location", url);
        return res;
    });

    // Callback от GitHub
    CROW_ROUTE(app, "/auth/github/callback")([&](const crow::request& req) {
        auto code = req.url_params.get("code");
        if (!code) return crow::response(400, "Нет параметра code");

        string body = "client_id=" + githubClientId + "&client_secret=" + githubClientSecret + "&code=" + string(code);
        string tokenResp = httpPost("https://github.com/login/oauth/access_token", body, {{"Accept", "application/json"}});

        json tokenJson = json::parse(tokenResp);
        if (!tokenJson.contains("access_token"))
            return crow::response(500, "Не получен access_token");

        string accessToken = tokenJson["access_token"];

        string userResp = httpGet("https://api.github.com/user", {{"Authorization", "token " + accessToken}});
        json userJson = json::parse(userResp);

        string login = userJson.value("login", "");
        string fullname = userJson.value("name", login);
        if (login.empty())
            return crow::response(500, "Не получен login");

        auto userOpt = db.getUserByLogin(login);
        UserInfo user;
        if (userOpt) {
            user = *userOpt;
        } else {
            int newId = db.createUser(login, fullname, "student");
            if (newId == -1) return crow::response(500, "Ошибка создания пользователя");
            user = {newId, fullname, login, "student", false};
        }

        if (user.is_blocked)
            return crow::response(403, "Пользователь заблокирован");

        string jwt = auth.generateToken(user);

        crow::json::wvalue result;
        result["token"] = jwt;
        result["role"] = user.role;
        result["fullname"] = user.fullname;
        result["login"] = user.login;
        return crow::response(result);
    });

    // Проверка токена
    CROW_ROUTE(app, "/validate")([&auth](const crow::request& req) {
        auto authHeader = req.get_header_value("Authorization");
        if (authHeader.empty() || authHeader.substr(0, 7) != "Bearer ")
            return crow::response(401, "Токен не передан или неверный формат");

        string token = authHeader.substr(7);
        auto userOpt = auth.validateToken(token);
        if (!userOpt)
            return crow::response(401, "Неверный или просроченный токен");

        UserInfo user = *userOpt;
        crow::json::wvalue resp;
        resp["valid"] = true;
        resp["user_id"] = user.id;
        resp["login"] = user.login;
        resp["role"] = user.role;
        resp["blocked"] = user.is_blocked;
        return crow::response(resp);
    });

    cout << "Сервер авторизации запущен на порту 8081" << endl;
    app.port(8081).multithreaded().run();
    return 0;
}