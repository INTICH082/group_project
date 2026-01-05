#include "utils.hpp"

using namespace std;

string random_string(size_t length) {
    static const string chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
    static mt19937 rng(random_device{}());
    uniform_int_distribution<size_t> dist(0, chars.size() - 1);

    string s(length, 0);
    for (size_t i = 0; i < length; ++i) {
        s[i] = chars[dist(rng)];
    }
    return s;
}

string base64_url_encode(const string& input) {
    static const string base64_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

    string encoded;
    int val = 0, valb = -6;
    for (unsigned char c : input) {
        val = (val << 8) + c;
        valb += 8;
        while (valb >= 0) {
            encoded.push_back(base64_chars[(val >> valb) & 0x3F]);
            valb -= 6;
        }
    }
    if (valb > -6) encoded.push_back(base64_chars[((val << 8) >> (valb + 8)) & 0x3F]);

    // Replace + and / with - and _
    replace(encoded.begin(), encoded.end(), '+', '-');
    replace(encoded.begin(), encoded.end(), '/', '_');

    // Remove padding '='
    encoded.erase(remove(encoded.begin(), encoded.end(), '='), encoded.end());

    return encoded;
}

string sha256(const string& input) {
    unsigned char hash[SHA256_DIGEST_LENGTH];
    SHA256_CTX sha256;
    SHA256_Init(&sha256);
    SHA256_Update(&sha256, input.c_str(), input.size());
    SHA256_Final(hash, &sha256);

    stringstream ss;
    for (int i = 0; i < SHA256_DIGEST_LENGTH; ++i) {
        ss << hex << setw(2) << setfill('0') << (int)hash[i];
    }
    return ss.str();
}