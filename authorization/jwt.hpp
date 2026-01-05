#pragma once

#include <string>

using namespace std;

string create_access_token(const string& user_id, const string& secret);

string create_refresh_token(const string& user_id, const string& secret);