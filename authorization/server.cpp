#include "server.h"
#include "auth.h"
#include "config.h"

// Кросс-платформенные заголовки для сетевых сокетов
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
#define close closesocket
#define SHUT_RDWR SD_BOTH
#else
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include <cerrno>
#include <cstdlib>
#endif

#include <iostream>
#include <sstream>

using namespace std;

// Определения для кросс-платформенности
#ifdef _WIN32
typedef SOCKET SocketType;
#define INVALID_SOCKET_VAL INVALID_SOCKET
#else
typedef int SocketType;
#define INVALID_SOCKET_VAL (-1)
#endif

void sendResponse(SocketType client, const string& content, bool json = false) {
    string response = "HTTP/1.1 200 OK\r\nContent-Type: " + 
                     string(json ? "application/json" : "text/plain") + 
                     "\r\nConnection: close\r\n\r\n" + content;
    send(client, response.c_str(), response.length(), 0);
}

void sendError(SocketType client, const string& error) {
    string response = "HTTP/1.1 400 Bad Request\r\nContent-Type: application/json\r\n\r\n{\"error\":\"" + error + "\"}";
    send(client, response.c_str(), response.length(), 0);
}

string readRequest(SocketType client) {
    char buffer[4096] = {0};
    int bytes = recv(client, buffer, sizeof(buffer), 0);
    return bytes > 0 ? string(buffer, bytes) : "";
}

void handleClient(SocketType client) {
    string request = readRequest(client);
    if (request.empty()) {
        close(client);
        return;
    }
    
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
        close(client);
        return;
    }
    
    if (path == "/auth/register" && method == "POST") {
        size_t body_start = request.find("\r\n\r\n");
        if (body_start == string::npos) {
            sendError(client, "Нет тела запроса");
            close(client);
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
        close(client);
        return;
    }
    
    if (path == "/auth/login" && method == "POST") {
        size_t body_start = request.find("\r\n\r\n");
        if (body_start == string::npos) {
            sendError(client, "Нет тела запроса");
            close(client);
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
        close(client);
        return;
    }
    
    if (path == "/auth/telegram" && method == "POST") {
        size_t body_start = request.find("\r\n\r\n");
        if (body_start == string::npos) {
            sendError(client, "Нет тела запроса");
            close(client);
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
        close(client);
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
        close(client);
        return;
    }
    
    if (path == "/auth/refresh" && method == "POST") {
        size_t body_start = request.find("\r\n\r\n");
        if (body_start == string::npos) {
            sendError(client, "Нет тела запроса");
            close(client);
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
        close(client);
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
        close(client);
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
        close(client);
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
        close(client);
        return;
    }
    
    if (path.find("/api/verify?") == 0) {
        size_t token_pos = path.find("token=");
        if (token_pos != string::npos) {
            string token = path.substr(token_pos + 6);
            string result = Auth::verifyToken(token);
            sendResponse(client, result, true);
        }
        close(client);
        return;
    }
    
    sendError(client, "Эндпоинт не найден");
    close(client);
}

void HttpServer::start(int port) {
#ifdef _WIN32
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        cerr << "Ошибка WSAStartup" << endl;
        return;
    }
#endif
    
    SocketType server = socket(AF_INET, SOCK_STREAM, 0);
    if (server == INVALID_SOCKET_VAL) {
        cerr << "Ошибка создания сокета" << endl;
#ifdef _WIN32
        WSACleanup();
#endif
        return;
    }
    
    // Позволяем переиспользовать порт
    int reuse = 1;
#ifdef _WIN32
    setsockopt(server, SOL_SOCKET, SO_REUSEADDR, (char*)&reuse, sizeof(reuse));
#else
    setsockopt(server, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
#endif
    
    sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(port);
    
    if (bind(server, (sockaddr*)&addr, sizeof(addr)) < 0) {
        cerr << "Ошибка bind" << endl;
        close(server);
#ifdef _WIN32
        WSACleanup();
#endif
        return;
    }
    
    if (listen(server, 10) < 0) {
        cerr << "Ошибка listen" << endl;
        close(server);
#ifdef _WIN32
        WSACleanup();
#endif
        return;
    }
    
    cout << "🚀 Модуль авторизации запущен на порту " << port << endl;
    cout << "📡 API доступен по адресу: http://localhost:" << port << endl;
    
    while (true) {
        sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);
        
        SocketType client = accept(server, (sockaddr*)&client_addr, &client_len);
        if (client == INVALID_SOCKET_VAL) {
            cerr << "Ошибка accept" << endl;
            continue;
        }
        
        handleClient(client);
    }
    
    close(server);
    
#ifdef _WIN32
    WSACleanup();
#endif
}