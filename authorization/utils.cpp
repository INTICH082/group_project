#define _HAS_STD_BYTE 0
#define byte win_byte
#include <windows.h>
#undef byte

#include "utils.h"
#include <curl/curl.h>
#include <iostream>
#include "json.hpp"  // Nlohmann JSON для парсинга ответов

using namespace std;
using nlohmann::json;

namespace {
    size_t WriteCallback(void* contents, size_t size, size_t nmemb, string* userp) {
        size_t realsize = size * nmemb;
        userp->append(static_cast<char*>(contents), realsize);
        return realsize;
    }
}

string httpGet(const string& url, const map<string, string>& headers) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        cerr << "curl_easy_init failed" << endl;
        return "";
    }

    string response;
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "auth_server/1.0");

    struct curl_slist *chunk = nullptr;
    for (const auto& h : headers) {
        string header = h.first + ": " + h.second;
        chunk = curl_slist_append(chunk, header.c_str());
    }
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, chunk);

    CURLcode res = curl_easy_perform(curl);
    if (res != CURLE_OK) {
        cerr << "curl_easy_perform() failed: " << curl_easy_strerror(res) << endl;
        response.clear();
    }

    curl_slist_free_all(chunk);
    curl_easy_cleanup(curl);

    return response;
}

string httpPost(const string& url, const string& body, const map<string, string>& headers) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        cerr << "curl_easy_init failed" << endl;
        return "";
    }

    string response;
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "auth_server/1.0");

    struct curl_slist *chunk = nullptr;
    for (const auto& h : headers) {
        string header = h.first + ": " + h.second;
        chunk = curl_slist_append(chunk, header.c_str());
    }
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, chunk);

    CURLcode res = curl_easy_perform(curl);
    if (res != CURLE_OK) {
        cerr << "curl_easy_perform() failed: " << curl_easy_strerror(res) << endl;
        response.clear();
    }

    curl_slist_free_all(chunk);
    curl_easy_cleanup(curl);

    return response;
}