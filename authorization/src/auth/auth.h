#pragma once
#include "database.h"
#include <string>
#include <optional>
#include <jwt-cpp/jwt.h>

class AuthService {
public:
    AuthService();
    string generateToken(const UserInfo& user);
    optional<UserInfo> validateToken(const string& token);

private:
    string secret;
};