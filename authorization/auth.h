#pragma once
#include <string>
#include <optional>
#include <jwt-cpp/jwt.h>

struct UserInfo {
    int id;
    string fullname;
    string login;
    string role;
    bool is_blocked;
};

class AuthService {
public:
    AuthService();
    string generateToken(const UserInfo& user);
    optional<UserInfo> validateToken(const string& token);

private:
    string secret;
};