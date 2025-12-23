#pragma once
#include <string>
#include <map>

using namespace std;

string httpGet(const string& url, const map<string, string>& headers = {});

string httpPost(const string& url, const string& body, const map<string, string>& headers = {});