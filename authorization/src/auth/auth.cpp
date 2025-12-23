#include "auth.h"
#include <cstdlib>
#include <iostream>

using namespace std;

AuthService::AuthService() {
    const char* sec = getenv("JWT_SECRET");
    if (sec) {
        secret = sec;
    } else {
        secret = "default_secret_измените_меня";
        cerr << "Предупреждение: используется секрет по умолчанию!" << endl;
    }
}

string AuthService::generateToken(const UserInfo& user) {
    auto token = jwt::create()
        .set_issuer("test-app-auth")
        .set_payload_claim("user_id", jwt::claim(to_string(user.id)))
        .set_payload_claim("login", jwt::claim(user.login))
        .set_payload_claim("fullname", jwt::claim(user.fullname))
        .set_payload_claim("role", jwt::claim(user.role))
        .set_payload_claim("blocked", jwt::claim(user.is_blocked ? "true" : "false"))
        .set_expires_at(chrono::system_clock::now() + chrono::hours{24})
        .sign(jwt::algorithm::hs256{secret});
    return token;
}

optional<UserInfo> AuthService::validateToken(const string& token) {
    try {
        auto decoded = jwt::decode(token);
        auto verifier = jwt::verify()
            .allow_algorithm(jwt::algorithm::hs256{secret})
            .with_issuer("test-app-auth");
        verifier.verify(decoded);

        UserInfo user;
        user.id = stoi(decoded.get_payload_claim("user_id").as_string());
        user.login = decoded.get_payload_claim("login").as_string();
        user.fullname = decoded.get_payload_claim("fullname").as_string();
        user.role = decoded.get_payload_claim("role").as_string();
        user.is_blocked = decoded.get_payload_claim("blocked").as_string() == "true";
        return user;
    } catch (...) {
        return nullopt;
    }
}