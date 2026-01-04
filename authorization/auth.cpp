#define _HAS_STD_BYTE 0
#define byte win_byte
#include <windows.h>
#undef byte

#include "auth.h"
#include <jwt-cpp/jwt.h>
#include <jwt-cpp/traits/kazuho-picojson/traits.h>
#include <iostream>
#include <chrono>
#include <string>

using namespace std;

string AuthService::generateToken(const UserInfo& user)
{
    cout << "Generating JWT for user: " << user.login << endl;

    auto now = chrono::system_clock::now();
    auto expires = now + chrono::hours(24);

    // Преобразуем bool в строку "true"/"false"
    string is_blocked_str = user.is_blocked ? "true" : "false";

    auto token = jwt::create()
        .set_issuer("auth-server")
        .set_subject(to_string(user.id))
        .set_issued_at(now)
        .set_expires_at(expires)
        .set_payload_claim("fullname", jwt::claim(user.fullname))
        .set_payload_claim("login", jwt::claim(user.login))
        .set_payload_claim("role", jwt::claim(user.role))
        .set_payload_claim("is_blocked", jwt::claim(is_blocked_str))  // ← string "true"/"false"
        .sign(jwt::algorithm::hs256{secret});

    return token;
}

optional<UserInfo> AuthService::validateToken(const string& token)
{
    try {
        cout << "Validating JWT token..." << endl;

        auto decoded = jwt::decode(token);

        // Проверка подписи и issuer
        jwt::verify()
            .allow_algorithm(jwt::algorithm::hs256{secret})
            .with_issuer("auth-server")
            .verify(decoded);

        // Проверка срока действия
        if (chrono::system_clock::now() > decoded.get_expires_at()) {
            cerr << "Token expired" << endl;
            return nullopt;
        }

        UserInfo user;
        user.id = stoi(decoded.get_subject());
        user.fullname = decoded.get_payload_claim("fullname").as_string();
        user.login = decoded.get_payload_claim("login").as_string();
        user.role = decoded.get_payload_claim("role").as_string();

        // is_blocked: строка "true"/"false" → bool
        string blocked_str = decoded.get_payload_claim("is_blocked").as_string();
        user.is_blocked = (blocked_str == "true");

        cout << "Token validated for user: " << user.login << endl;
        return user;
    }
    catch (const jwt::error::token_verification_exception& e) {
        cerr << "Token verification failed: " << e.what() << endl;
        return nullopt;
    }
    catch (const exception& e) {
        cerr << "Token validation error: " << e.what() << endl;
        return nullopt;
    }
}