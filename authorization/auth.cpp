#include "auth.h"
#include <jwt-cpp/jwt.h>

using namespace std;

string AuthService::generateToken(const UserInfo& user)
{
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c";
}

optional<UserInfo> AuthService::validateToken(const string& token)
{
    return UserInfo{1, "Test User", "test", "student", false};
}