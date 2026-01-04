#define _HAS_STD_BYTE 0
#define byte win_byte
#include <windows.h>
#undef byte

#pragma once

#include <jwt-cpp/jwt.h>
#include <chrono>
#include <string>

using namespace std;

string create_access_token(const string& user_id, const string& secret);

string create_refresh_token(const string& user_id, const string& secret);