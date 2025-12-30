#include "utils.h"
#include <curl/curl.h>
#include <iostream>

using namespace std;

static size_t writeCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    ((string*)userp)->append((char*)contents, size * nmemb);
    return size * nmemb;
}

string httpGet(const string& url, const map<string, string>& headers) {
    CURL* curl = curl_easy_init();
    if (!curl) return "";

    string readBuffer;
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &readBuffer);

    struct curl_slist* headerList = nullptr;
    for (const auto& h : headers) {
        string header = h.first + ": " + h.second;
        headerList = curl_slist_append(headerList, header.c_str());
    }
    if (headerList) curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headerList);

    CURLcode res = curl_easy_perform(curl);

    if (headerList) curl_slist_free_all(headerList);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        cerr << "curl GET failed: " << curl_easy_strerror(res) << endl;
        return "";
    }
    return readBuffer;
}

string httpPost(const string& url, const string& body, const map<string, string>& headers) {
    CURL* curl = curl_easy_init();
    if (!curl) return "";

    string readBuffer;
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &readBuffer);

    struct curl_slist* headerList = nullptr;
    headerList = curl_slist_append(headerList, "Content-Type: application/x-www-form-urlencoded");
    for (const auto& h : headers) {
        string header = h.first + ": " + h.second;
        headerList = curl_slist_append(headerList, header.c_str());
    }
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headerList);

    CURLcode res = curl_easy_perform(curl);

    curl_slist_free_all(headerList);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        cerr << "curl POST failed: " << curl_easy_strerror(res) << endl;
        return "";
    }
    return readBuffer;
}