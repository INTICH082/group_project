#include "utils.h"
#include <openssl/sha.h>
#include <sstream>
#include <iomanip>
#include <vector>

using namespace std;

string Utils::base64_encode(const string& input) {
    static const string chars = 
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789+/";
    
    string output;
    int i = 0;
    unsigned char array_3[3];
    unsigned char array_4[4];
    
    for (unsigned char c : input) {
        array_3[i++] = c;
        if (i == 3) {
            array_4[0] = (array_3[0] & 0xfc) >> 2;
            array_4[1] = ((array_3[0] & 0x03) << 4) + ((array_3[1] & 0xf0) >> 4);
            array_4[2] = ((array_3[1] & 0x0f) << 2) + ((array_3[2] & 0xc0) >> 6);
            array_4[3] = array_3[2] & 0x3f;
            
            for(i = 0; i < 4; i++) output += chars[array_4[i]];
            i = 0;
        }
    }
    
    if (i) {
        for(int j = i; j < 3; j++) array_3[j] = '\0';
        
        array_4[0] = (array_3[0] & 0xfc) >> 2;
        array_4[1] = ((array_3[0] & 0x03) << 4) + ((array_3[1] & 0xf0) >> 4);
        array_4[2] = ((array_3[1] & 0x0f) << 2) + ((array_3[2] & 0xc0) >> 6);
        array_4[3] = array_3[2] & 0x3f;
        
        for (int j = 0; j < i + 1; j++) output += chars[array_4[j]];
        while(i++ < 3) output += '=';
    }
    
    return output;
}

string Utils::base64_decode(const string& input) {
    static const string chars = 
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789+/";
    
    string output;
    vector<int> table(256, -1);
    for (int i = 0; i < 64; i++) table[chars[i]] = i;
    
    int val = 0, valb = -8;
    for (unsigned char c : input) {
        if (table[c] == -1) break;
        val = (val << 6) + table[c];
        valb += 6;
        if (valb >= 0) {
            output += char((val >> valb) & 0xFF);
            valb -= 8;
        }
    }
    
    return output;
}

string Utils::sha256(const string& input) {
    unsigned char hash[SHA256_DIGEST_LENGTH];
    SHA256_CTX sha256;
    SHA256_Init(&sha256);
    SHA256_Update(&sha256, input.c_str(), input.size());
    SHA256_Final(hash, &sha256);
    
    stringstream ss;
    for(int i = 0; i < SHA256_DIGEST_LENGTH; i++) {
        ss << hex << setw(2) << setfill('0') << (int)hash[i];
    }
    return ss.str();
}