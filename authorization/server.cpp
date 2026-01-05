#include "server.h"
#include "auth.h"
#include <iostream>
#include <sstream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <cstring>

using namespace std;

map<string, function<void(const string&, string&)>> postHandlers;
map<string, function<void(const string&, string&)>> getHandlers;

void Server::post(const string& path, function<void(const string&, string&)> handler) {
    postHandlers[path] = handler;
}

void Server::get(const string& path, function<void(const string&, string&)> handler) {
    getHandlers[path] = handler;
}

void Server::handleRequest(const string& method, const string& path,
                          const string& body, string& response) {
    response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n";
    
    if (method == "POST") {
        auto it = postHandlers.find(path);
        if (it != postHandlers.end()) {
            string json_resp;
            it->second(body, json_resp);
            response += json_resp;
            return;
        }
    }
    else if (method == "GET") {
        auto it = getHandlers.find(path);
        if (it != getHandlers.end()) {
            string json_resp;
            it->second(body, json_resp);
            response += json_resp;
            return;
        }
    }
    
    response = "HTTP/1.1 404 Not Found\r\n\r\n";
}

void Server::start(int port) {
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in address;
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(port);
    
    bind(server_fd, (sockaddr*)&address, sizeof(address));
    listen(server_fd, 5);
    
    cout << "Server running on http://localhost:" << port << endl;
    
    while (true) {
        sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);
        int client_fd = accept(server_fd, (sockaddr*)&client_addr, &client_len);
        
        char buffer[4096];
        read(client_fd, buffer, sizeof(buffer));
        
        // Парсинг запроса
        string request(buffer);
        stringstream ss(request);
        string method, path, version;
        ss >> method >> path >> version;
        
        // Поиск тела запроса
        string body;
        size_t body_pos = request.find("\r\n\r\n");
        if (body_pos != string::npos) {
            body = request.substr(body_pos + 4);
        }
        
        // Обработка
        string response;
        handleRequest(method, path, body, response);
        
        // Отправка ответа
        write(client_fd, response.c_str(), response.size());
        close(client_fd);
    }
}