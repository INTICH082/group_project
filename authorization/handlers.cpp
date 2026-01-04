#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#endif

#include "handlers.hpp"
#include "config.hpp"
#include "utils.hpp"
#include "jwt.hpp"
#include "mongo.hpp"
#include <crow.h>

using namespace std;

void register_routes(crow::SimpleApp& app) {
    init_mongo_ttl();
    CROW_ROUTE(app, "/login").methods(crow::HTTPMethod::Get)
    ([](const crow::request& req) {
        auto token_ptr = req.url_params.get("token");
        auto type_ptr  = req.url_params.get("type");
        if (!token_ptr || !type_ptr) {
            return crow::response(400, "Обязательны параметры token и type");
        }

        string token = token_ptr;
        string type  = type_ptr;

        json state = {{"status", "pending"}};

        if (type == "github" || type == "yandex") {
            string verifier = random_string(43);
            string challenge = base64_url_encode(sha256(verifier));

            state["code_verifier"] = verifier;
            state["provider"] = type;

            string auth_url;
            if (type == "github") {
                auth_url = "https://github.com/login/oauth/authorize"
                           "?client_id=" + cfg.github_client_id +
                           "&redirect_uri=" + cfg.redirect_uri +
                           "&scope=user:email" +
                           "&state=" + token +
                           "&code_challenge=" + challenge +
                           "&code_challenge_method=S256";
            } else {
                auth_url = "https://oauth.yandex.ru/authorize"
                           "?response_type=code"
                           "&client_id=" + cfg.yandex_client_id +
                           "&redirect_uri=" + cfg.redirect_uri +
                           "&state=" + token;
            }

            save_login_state(token, state);
            crow::response res(302);
            res.set_header("Location", auth_url);
            return res;
        }

        if (type == "code") {
            string code = random_string(6);
            // делаем только цифры (если нужно строго 6 цифр)
            code = string(6, '0') + code;
            code = code.substr(code.size() - 6);
            state["code"] = code;
            state["provider"] = "code";

            save_login_state(token, state);

            crow::json::wvalue resp;
            resp["message"] = "Введите код в клиенте";
            resp["code"] = code;
            return crow::response(resp);
        }

        return crow::response(400, "Недопустимый тип авторизации");
    });


    CROW_ROUTE(app, "/callback").methods(crow::HTTPMethod::Get)
    ([](const crow::request& req) {
        auto code_ptr  = req.url_params.get("code");
        auto state_ptr = req.url_params.get("state");

        if (!code_ptr || !state_ptr) {
            return crow::response(400, "Отсутствует code или state");
        }

        string code = code_ptr;
        string token = state_ptr;

        auto state_opt = get_login_state(token);
        if (!state_opt || state_opt["status"] != "pending") {
            return crow::response(400, "Неверный или истёкший state");
        }

        json state = state_opt;

        // TODO: здесь должен быть реальный обмен code на токен
        // Пока оставляем заглушку с тестовым user_id

        string user_id = "user_" + random_string(12);

        string access_token  = create_access_token(user_id, cfg.jwt_secret);
        string refresh_token = create_refresh_token(user_id, cfg.jwt_secret);

        json final_state = state;
        final_state["status"] = "success";
        final_state["access_token"] = access_token;
        final_state["refresh_token"] = refresh_token;

        save_login_state(token, final_state, 60);

        return crow::response("Авторизация выполнена. Можете закрыть это окно.");
    });


    CROW_ROUTE(app, "/check").methods(crow::HTTPMethod::Get)
    ([](const crow::request& req) {
        auto token_ptr = req.url_params.get("token");
        if (!token_ptr) return crow::response(400, "Требуется token");

        string token = token_ptr;
        auto state_opt = get_login_state(token);

        if (!state_opt) {
            return crow::response(404, "Состояние не найдено или истекло");
        }

        json state = state_opt;

        crow::json::wvalue resp;
        resp["status"] = state["status"].get<std::string>();

        if (state["status"].get<std::string>() == "success") {
            resp["access_token"]  = state["access_token"].get<std::string>();
            resp["refresh_token"] = state["refresh_token"].get<std::string>();
        }

        return crow::response(resp);
    });
}