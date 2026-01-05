#pragma once
#include <string>

using namespace std;

namespace Utils {
    string base64_encode(const string& input);
    string base64_decode(const string& input);
    string sha256(const string& input);
}