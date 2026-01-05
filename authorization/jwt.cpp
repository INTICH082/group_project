#include "jwt.hpp"
#include "config.hpp"

#include <jwt-cpp/jwt.h>
#include <jwt-cpp/traits/nlohmann-json/traits.h>
#include <chrono>

using namespace std;
using traits = jwt::traits::nlohmann_json;

string create_access_token(const string& user_id, const string& secret) {
    return jwt::create<traits>()
        .set_issuer("auth")
        .set_type("JWS")
        .set_subject(user_id)
        .set_issued_at(chrono::system_clock::now())
        .set_expires_at(chrono::system_clock::now() + chrono::minutes{15})
        .sign(jwt::algorithm::hs256{secret});
}

string create_refresh_token(const string& user_id, const string& secret) {
    return jwt::create<traits>()
        .set_issuer("auth")
        .set_type("JWS")
        .set_subject(user_id)
        .set_issued_at(chrono::system_clock::now())
        .set_expires_at(chrono::system_clock::now() + chrono::hours{24 * 7})  // 7 дней = 168 часов
        .sign(jwt::algorithm::hs256{secret});
}