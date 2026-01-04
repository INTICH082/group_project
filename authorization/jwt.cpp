#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#endif

#include "jwt.hpp"
#include "config.hpp"

string create_access_token(const string& user_id, const string& secret) {
    return jwt::create()
        .set_issuer("auth")
        .set_type("JWS")
        .set_payload_claim("sub", jwt::claim(user_id))
        .set_issued_at(chrono::system_clock::now())
        .set_expires_at(chrono::system_clock::now() + chrono::minutes(1))
        .sign(jwt::algorithm::hs256{secret});
}

string create_refresh_token(const string& user_id, const string& secret) {
    return jwt::create()
        .set_issuer("auth")
        .set_type("JWS")
        .set_payload_claim("sub", jwt::claim(user_id))
        .set_issued_at(chrono::system_clock::now())
        .set_expires_at(chrono::system_clock::now() + chrono::hours(24 * 7))
        .sign(jwt::algorithm::hs256{secret});
}