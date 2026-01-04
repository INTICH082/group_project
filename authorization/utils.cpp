#define _HAS_STD_BYTE 0
#define byte win_byte
#include <windows.h>
#undef byte

#include "utils.h"
#include <curl/curl.h>
#include "json.hpp"

using namespace std;
using nlohmann::json;

namespace {
    size_t WriteCallback(void* contents, size_t size, size_t nmemb, string* userp) {
        userp->append(static_cast<char*>(contents), size * nmemb);
        return size * nmemb;
    }
}

string httpGet(const string& url, const map<string, string>& headers) {
    CURL* curl = curl_easy_init();
    if (!curl) return "";

    string response;
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "auth_server/1.0");

    struct curl_slist *chunk = nullptr;
    for (const auto& h : headers) chunk = curl_slist_append(chunk, (h.first + ": " + h.second).c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, chunk);

    curl_easy_perform(curl);

    curl_slist_free_all(chunk);
    curl_easy_cleanup(curl);

    return response;
}

string httpPost(const string& url, const string& body, const map<string, string>& headers) {
    CURL* curl = curl_easy_init();
    if (!curl) return "";

    string response;
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "auth_server/1.0");

    struct curl_slist *chunk = nullptr;
    for (const auto& h : headers) chunk = curl_slist_append(chunk, (h.first + ": " + h.second).c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, chunk);

    curl_easy_perform(curl);

    curl_slist_free_all(chunk);
    curl_easy_cleanup(curl);

    return response;
}