#pragma once
#include <functional>
#include <string>

using namespace std;

class Server {
public:
    void start(int port = 8080);
    
    void post(const string& path, function<void(const string&, string&)> handler);
    void get(const string& path, function<void(const string&, string&)> handler);
    
private:
    void handleRequest(const string& method, const string& path, 
                      const string& body, string& response);
};