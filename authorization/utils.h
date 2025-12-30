#pragma once
#include <string>
#include <map>

string httpGet(const string& url, const map<string, string>& headers = {});
string httpPost(const string& url, const string& body, const map<string, string>& headers = {});