#include <openssl/sha.h>
#include <sstream>
#include <iomanip>
#include <random>
#include <chrono>

using namespace std;

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

string generate_token() {
    static mt19937_64 rng(chrono::high_resolution_clock::now().time_since_epoch().count());
    uniform_int_distribution<uint64_t> dist;
    stringstream ss;
    ss << hex << dist(rng) << dist(rng);
    return ss.str();
}