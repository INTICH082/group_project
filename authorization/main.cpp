#define _HAS_STD_BYTE 0

#include "crow.h"         
#include "auth.h"
#include "database.h"
#include "utils.h"

#include <string>
#include <map>
#include <cstdlib>      // getenv
#include <exception>
#include "json.hpp"     // для парсинга JSON от GitHub

using namespace std;
using nlohmann::json;

int main() {
    const char* github_client_id     = getenv("GITHUB_CLIENT_ID");
    const char* github_client_secret = getenv("GITHUB_CLIENT_SECRET");
    const char* db_password          = getenv("DB_PASSWORD");
    const char* jwt_secret           = getenv("JWT_SECRET");

    if (!github_client_id || !github_client_secret || !db_password || !jwt_secret) {
        return 1;
    }

    Database db("localhost", "root", db_password, "Project");
    AuthService auth(jwt_secret);

    crow::SimpleApp app;

    CROW_ROUTE(app, "/test")([](){
        return "Server is alive!";
    });

    CROW_ROUTE(app, "/auth/github")([&](){
        string oauth_url = "https://github.com/login/oauth/authorize?client_id=" + string(github_client_id) + "&redirect_uri=http://localhost:8081/auth/github/callback";
        crow::response res;
        res.code = 302;
        res.add_header("Location", oauth_url);
        return res;
    });

    CROW_ROUTE(app, "/auth/github/callback")([&](const crow::request& req){
        auto params = req.url_params;
        string code = params.get("code");

        if (code.empty()) return crow::response(400, "No code provided");

        string token_url = "https://github.com/login/oauth/access_token";
        map<string, string> post_data = {
            {"client_id", github_client_id},
            {"client_secret", github_client_secret},
            {"code", code}
        };
        string token_response = httpPost(token_url, "", post_data);

        json token_json = json::parse(token_response);
        string access_token = token_json["access_token"];

        if (access_token.empty()) return crow::response(500, "Failed to get access token");

        string user_url = "https://api.github.com/user";
        map<string, string> headers = {{"Authorization", "Bearer " + access_token}};
        string user_response = httpGet(user_url, headers);

        json user_json = json::parse(user_response);

        UserInfo user;
        user.login = user_json["login"];
        user.fullname = user_json["name"];
        user.role = "student";
        user.is_blocked = false;
        user.id = db.createUser(user.login, user.fullname, user.role);

        string jwt_token = auth.generateToken(user);

        return crow::response(200, "JWT Token: " + jwt_token);
    });

    CROW_ROUTE(app, "/profile")([&](const crow::request& req){
        auto auth_header = req.get_header_value("Authorization");
        if (auth_header.empty() || auth_header.find("Bearer ") != 0) return crow::response(401, "Unauthorized");

        string token = auth_header.substr(7);
        auto user_opt = auth.validateToken(token);
        if (!user_opt) return crow::response(401, "Invalid token");

        return crow::response(200, "Welcome, " + user_opt->fullname);
    });

    app.port(8081).multithreaded().run();
    return 0;
}