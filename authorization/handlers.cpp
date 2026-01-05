#include "handlers.hpp"
#include "config.hpp"
#include "utils.hpp"
#include "jwt.hpp"
#include "mysql.hpp"
#include <crow.h>
#include <cpr/cpr.h>
#include <nlohmann/json.hpp>
#include <iostream>
#include <chrono>

using namespace std;
using json = nlohmann::json;

MySQLDB db(cfg.mysql_host, cfg.mysql_user, cfg.mysql_password, cfg.mysql_db, cfg.mysql_port);

void save_login_state(const string& token, const json& data, int ttl_seconds) {
    auto now = chrono::system_clock::now();
    auto expires = now + chrono::seconds(ttl_seconds);

    string data_str = data.dump();

    string query = "INSERT INTO users (fullname, oauth_state, oauth_expires) VALUES ('" + token + "', '" + data_str + "', FROM_UNIXTIME(" + to_string(chrono::duration_cast<chrono::seconds>(expires.time_since_epoch()).count()) + ")) ON DUPLICATE KEY UPDATE oauth_state = '" + data_str + "', oauth_expires = FROM_UNIXTIME(" + to_string(chrono::duration_cast<chrono::seconds>(expires.time_since_epoch()).count()) + ")";

    db.execute(query);
}

json get_login_state(const string& token) {
    string query = "SELECT oauth_state, UNIX_TIMESTAMP(oauth_expires) AS expires_unix FROM users WHERE fullname = '" + token + "'";
    auto results = db.fetch_all(query);

    if (results.empty()) return json{};

    uint64_t expires_unix = stoull(results[0]["expires_unix"]);
    uint64_t now_unix = chrono::duration_cast<chrono::seconds>(chrono::system_clock::now().time_since_epoch()).count();

    if (expires_unix < now_unix) {
        db.execute("UPDATE users SET oauth_state = NULL, oauth_expires = NULL WHERE fullname = '" + token + "'");
        return json{};
    }

    string data_str = results[0]["oauth_state"];
    return json::parse(data_str);
}

void register_routes(crow::SimpleApp& app) {
    CROW_ROUTE(app, "/login").methods("GET"_method)
    ([](const crow::request& req) {
        string token = req.url_params.get("token");
        string type = req.url_params.get("type");
        if (token.empty() || type.empty()) {
            return crow::response(400, "Параметры token и type обязательны");
        }

        json state = {{"status", "pending"}, {"provider", type}};

        string auth_url;
        if (type == "github") {
            string verifier = random_string(43);
            string challenge = base64_url_encode(sha256(verifier));
            state["code_verifier"] = verifier;

            auth_url = "https://github.com/login/oauth/authorize?"
                       "client_id=" + cfg.github_client_id +
                       "&redirect_uri=" + crow::utility::urlencode(cfg.redirect_uri) +
                       "&scope=user:email&state=" + token +
                       "&code_challenge=" + challenge + "&code_challenge_method=S256";
        } else if (type == "yandex") {
            auth_url = "https://oauth.yandex.ru/authorize?"
                       "response_type=code&client_id=" + cfg.yandex_client_id +
                       "&redirect_uri=" + crow::utility::urlencode(cfg.redirect_uri) +
                       "&state=" + token;
        } else {
            return crow::response(400, "Неподдерживаемый провайдер");
        }

        save_login_state(token, state, 600);

        crow::response res(302);
        res.set_header("Location", auth_url);
        return res;
    });

    CROW_ROUTE(app, "/callback").methods("GET"_method)
    ([](const crow::request& req) {
        string code = req.url_params.get("code");
        string state_token = req.url_params.get("state");
        if (code.empty() || state_token.empty()) {
            return crow::response(400, "code или state отсутствует");
        }

        json state = get_login_state(state_token);
        if (state.empty() || state["status"] != "pending") {
            return crow::response(400, "Неверное или истёкшее состояние");
        }

        string provider = state["provider"].get<string>();
        string user_id;

        try {
            if (provider == "github") {
                string verifier = state["code_verifier"].get<string>();

                auto r = cpr::Post(cpr::Url{"https://github.com/login/oauth/access_token"},
                                   cpr::Payload{{"client_id", cfg.github_client_id},
                                                {"client_secret", cfg.github_client_secret},
                                                {"code", code},
                                                {"redirect_uri", cfg.redirect_uri},
                                                {"code_verifier", verifier}},
                                   cpr::Header{{"Accept", "application/json"}});

                if (r.status_code != 200) {
                    throw runtime_error("GitHub token error");
                }

                json token_json = json::parse(r.text);
                string access_token = token_json["access_token"].get<string>();

                auto u = cpr::Get(cpr::Url{"https://api.github.com/user"},
                                  cpr::Header{{"Authorization", "token " + access_token},
                                              {"User-Agent", "auth-server"}});

                if (u.status_code != 200) {
                    throw runtime_error("GitHub user error");
                }

                json user_json = json::parse(u.text);
                user_id = "github:" + to_string(user_json["id"].get<int64_t>());
            } else if (provider == "yandex") {
                auto r = cpr::Post(cpr::Url{"https://oauth.yandex.ru/token"},
                                   cpr::Payload{{"grant_type", "authorization_code"},
                                                {"code", code},
                                                {"client_id", cfg.yandex_client_id},
                                                {"client_secret", cfg.yandex_client_secret},
                                                {"redirect_uri", cfg.redirect_uri}});

                if (r.status_code != 200) {
                    throw runtime_error("Yandex token error");
                }

                json token_json = json::parse(r.text);
                string access_token = token_json["access_token"].get<string>();

                auto u = cpr::Get(cpr::Url{"https://login.yandex.ru/info"},
                                  cpr::Header{{"Authorization", "OAuth " + access_token}});

                if (u.status_code != 200) {
                    throw runtime_error("Yandex user error");
                }

                json user_json = json::parse(u.text);
                user_id = "yandex:" + user_json["id"].get<string>();
            }
        } catch (const exception& e) {
            cerr << "OAuth error: " + string(e.what()) << endl;
            return crow::response(500, "Ошибка авторизации у провайдера");
        }

        string access_token = create_access_token(user_id, cfg.jwt_secret);
        string refresh_token = create_refresh_token(user_id, cfg.jwt_secret);

        db.execute("UPDATE users SET access_token = '" + access_token + "', refresh_token = '" + refresh_token + "', oauth_state = NULL, oauth_expires = NULL WHERE fullname = '" + state_token + "'");

        return crow::response("<h2>Авторизация успешна!</h2><p>Можете закрыть окно.</p>");
    });

    CROW_ROUTE(app, "/check").methods("GET"_method)
    ([](const crow::request& req) {
        string token = req.url_params.get("token");
        if (token.empty()) return crow::response(400, "token обязателен");

        json state = get_login_state(token);
        crow::json::wvalue resp;
        resp["status"] = state.value("status", "expired");

        if (state["status"] == "success") {
            resp["access_token"] = state["access_token"];
            resp["refresh_token"] = state["refresh_token"];
            resp["user_id"] = state["user_id"];
        }

        return crow::response(resp);
    });
}