#define _HAS_STD_BYTE 0
#define byte win_byte
#include <windows.h>
#undef byte

#include "auth.h"
#include <jwt-cpp/jwt.h>
#include <jwt-cpp/traits/kazuho-picojson/traits.h>
#include <chrono>

using namespace std;

string AuthService::generateToken(const UserInfo& user) {
    auto now = chrono::system_clock::now();
    auto expires = now + chrono::hours(24);

    string is_blocked_str = user.is_blocked ? "true" : "false";

    auto token = jwt::create()
        .set_issuer("auth-server")
        .set_subject(to_string(user.id))
        .set_issued_at(now)
        .set_expires_at(expires)
        .set_payload_claim("fullname", jwt::claim(user.fullname))
        .set_payload_claim("login", jwt::claim(user.login))
        .set_payload_claim("role", jwt::claim(user.role))
        .set_payload_claim("is_blocked", jwt::claim(is_blocked_str))
        .sign(jwt::algorithm::hs256{secret});

    return token;
}

optional<UserInfo> AuthService::validateToken(const string& token) {
    try {
        auto decoded = jwt::decode(token);

        jwt::verify()
            .allow_algorithm(jwt::algorithm::hs256{secret})
            .with_issuer("auth-server")
            .verify(decoded);

        if (chrono::system_clock::now() > decoded.get_expires_at()) {
            return nullopt;
        }

        UserInfo user;
        user.id = stoi(decoded.get_subject());
        user.fullname = decoded.get_payload_claim("fullname").as_string();
        user.login = decoded.get_payload_claim("login").as_string();
        user.role = decoded.get_payload_claim("role").as_string();
        string blocked_str = decoded.get_payload_claim("is_blocked").as_string();
        user.is_blocked = (blocked_str == "true");

        return user;
    } catch (...) {
        return nullopt;
    }
}