#pragma once

#include <string>
#include <optional>

using namespace std;

struct UserInfo {
    int id;
    string fullname;
    string login;
    string role;
    bool is_blocked;
};

class AuthService {
public:
    AuthService(const string& jwt_secret) : secret(jwt_secret) {}

    string generateToken(const UserInfo& user);
    optional<UserInfo> validateToken(const string& token);

private:
    string secret;
};