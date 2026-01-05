#pragma once

#include <string>
#include <random>
#include <iomanip>
#include <sstream>
#include <openssl/sha.h>

using namespace std;

string random_string(size_t length);

string base64_url_encode(const string& input);

string sha256(const string& input);