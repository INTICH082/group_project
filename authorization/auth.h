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
    AuthService() = default;

    optional<UserInfo> authenticate(const string& login, const string& password);

private:
};