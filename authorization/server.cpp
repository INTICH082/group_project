#include "server.h"
#include "auth.h"
#include "config.h"
#include <winsock2.h>
#include <ws2tcpip.h>
#include <iostream>
#include <sstream>

using namespace std;

#pragma comment(lib, "ws2_32.lib")

void sendResponse(int client, const string& content, bool json = false) {
    string response = "HTTP/1.1 200 OK\r\nContent-Type: " + 
                     string(json ? "application/json" : "text/plain") + 
                     "\r\nConnection: close\r\n\r\n" + content;
    send(client, response.c_str(), response.length(), 0);
}

void sendError(int client, const string& error) {
    string response = "HTTP/1.1 400 Bad Request\r\nContent-Type: application/json\r\n\r\n{\"error\":\"" + error + "\"}";
    send(client, response.c_str(), response.length(), 0);
}

string readRequest(int client) {
    char buffer[4096] = {0};
    int bytes = recv(client, buffer, sizeof(buffer), 0);
    return bytes > 0 ? string(buffer, bytes) : "";
}

void handleClient(int client) {
    string request = readRequest(client);
    if (request.empty()) return;
    
    istringstream ss(request);
    string method, path;
    ss >> method >> path;
    
    cout << method << " " << path << endl;
    
    if (path == "/" || path == "/api") {
        string apiInfo = R"({
    "auth_module": "v1.0",
    "endpoints": {
        "POST /auth/register": "login,password,fullname,email",
        "POST /auth/login": "login,password",
        "POST /auth/telegram": "telegram_id,name",
        "GET /auth/verify": "token",
        "POST /auth/refresh": "refresh_token",
        "GET /auth/oauth": "login_token",
        "GET /auth/callback": "code,state"
    }
})";
        sendResponse(client, apiInfo, true);
        return;
    }
    
    if (path == "/auth/register" && method == "POST") {
        size_t body_start = request.find("\r\n\r\n");
        if (body_start == string::npos) {
            sendError(client, "Нет тела запроса");
            return;
        }
        
        string body = request.substr(body_start + 4);
        istringstream iss(body);
        string pair, login, password, fullname, email;
        
        while (getline(iss, pair, '&')) {
            size_t eq = pair.find('=');
            if (eq != string::npos) {
                string key = pair.substr(0, eq);
                string value = pair.substr(eq + 1);
                
                if (key == "login") login = value;
                else if (key == "password") password = value;
                else if (key == "fullname") fullname = value;
                else if (key == "email") email = value;
            }
        }
        
        string result = Auth::registerUser(login, password, fullname, email);
        sendResponse(client, result, true);
        return;
    }
    
    if (path == "/auth/login" && method == "POST") {
        size_t body_start = request.find("\r\n\r\n");
        if (body_start == string::npos) {
            sendError(client, "Нет тела запроса");
            return;
        }
        
        string body = request.substr(body_start + 4);
        istringstream iss(body);
        string pair, login, password;
        
        while (getline(iss, pair, '&')) {
            size_t eq = pair.find('=');
            if (eq != string::npos) {
                string key = pair.substr(0, eq);
                string value = pair.substr(eq + 1);
                if (key == "login") login = value;
                else if (key == "password") password = value;
            }
        }
        
        string result = Auth::loginUser(login, password);
        sendResponse(client, result, true);
        return;
    }
    
    if (path == "/auth/telegram" && method == "POST") {
        size_t body_start = request.find("\r\n\r\n");
        if (body_start == string::npos) {
            sendError(client, "Нет тела запроса");
            return;
        }
        
        string body = request.substr(body_start + 4);
        istringstream iss(body);
        string pair, telegram_id, name;
        
        while (getline(iss, pair, '&')) {
            size_t eq = pair.find('=');
            if (eq != string::npos) {
                string key = pair.substr(0, eq);
                string value = pair.substr(eq + 1);
                if (key == "telegram_id") telegram_id = value;
                else if (key == "name") name = value;
            }
        }
        
        string result = Auth::telegramAuth(telegram_id, name);
        sendResponse(client, result, true);
        return;
    }
    
    if (path.find("/auth/verify?") == 0) {
        size_t token_pos = path.find("token=");
        if (token_pos != string::npos) {
            string token = path.substr(token_pos + 6);
            string result = Auth::verifyToken(token);
            sendResponse(client, result, true);
        } else {
            sendError(client, "Нет токена");
        }
        return;
    }
    
    if (path == "/auth/refresh" && method == "POST") {
        size_t body_start = request.find("\r\n\r\n");
        if (body_start == string::npos) {
            sendError(client, "Нет тела запроса");
            return;
        }
        
        string body = request.substr(body_start + 4);
        size_t token_pos = body.find("refresh_token=");
        if (token_pos != string::npos) {
            string refresh_token = body.substr(token_pos + 13);
            string result = Auth::refreshToken(refresh_token);
            sendResponse(client, result, true);
        } else {
            sendError(client, "Нет refresh_token");
        }
        return;
    }
    
    if (path.find("/auth/oauth?") == 0) {
        size_t token_pos = path.find("login_token=");
        if (token_pos != string::npos) {
            string token = path.substr(token_pos + 12);
            string result = Auth::startOAuth(token);
            sendResponse(client, result, true);
        } else {
            sendError(client, "Нет login_token");
        }
        return;
    }
    
    if (path.find("/auth/callback?") == 0) {
        size_t code_pos = path.find("code=");
        size_t state_pos = path.find("&state=");
        
        if (code_pos != string::npos) {
            string code, state;
            
            if (state_pos != string::npos) {
                code = path.substr(code_pos + 5, state_pos - (code_pos + 5));
                state = path.substr(state_pos + 7);
            } else {
                code = path.substr(code_pos + 5);
            }
            
            string result = Auth::handleGitHubCallback(code, state);
            sendResponse(client, result, true);
        } else {
            sendError(client, "Нет кода");
        }
        return;
    }
    
    if (path == "/api/telegram" && method == "POST") {
        size_t body_start = request.find("\r\n\r\n");
        if (body_start != string::npos) {
            string body = request.substr(body_start + 4);
            istringstream iss(body);
            string pair, telegram_id, name;
            
            while (getline(iss, pair, '&')) {
                size_t eq = pair.find('=');
                if (eq != string::npos) {
                    string key = pair.substr(0, eq);
                    string value = pair.substr(eq + 1);
                    if (key == "telegram_id") telegram_id = value;
                    else if (key == "name") name = value;
                }
            }
            
            string result = Auth::telegramAuth(telegram_id, name);
            sendResponse(client, result, true);
        }
        return;
    }
    
    if (path.find("/api/verify?") == 0) {
        size_t token_pos = path.find("token=");
        if (token_pos != string::npos) {
            string token = path.substr(token_pos + 6);
            string result = Auth::verifyToken(token);
            sendResponse(client, result, true);
        }
        return;
    }
    
    sendError(client, "Эндпоинт не найден");
}

void HttpServer::start(int port) {
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        cerr << "Ошибка WSAStartup" << endl;
        return;
    }
    
    SOCKET server = socket(AF_INET, SOCK_STREAM, 0);
    
    sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(port);
    
    bind(server, (sockaddr*)&addr, sizeof(addr));
    listen(server, 10);
    
    cout << "🚀 Модуль авторизации запущен на порту " << port << endl;
    cout << "📡 API доступен по адресу: http://localhost:" << port << endl;
    
    while (true) {
        SOCKET client = accept(server, nullptr, nullptr);
        if (client != INVALID_SOCKET) {
            handleClient(client);
            closesocket(client);
        }
    }
    
    closesocket(server);
    WSACleanup();
}