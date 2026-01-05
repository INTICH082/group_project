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
    string response = "HTTP/1.1 200 OK\r\n";
    response += "Content-Type: " + string(json ? "application/json" : "text/html; charset=utf-8") + "\r\n";
    response += "Access-Control-Allow-Origin: *\r\n";
    response += "Connection: close\r\n";
    response += "\r\n" + content;
    
    send(client, response.c_str(), response.length(), 0);
}

string readRequest(int client) {
    char buffer[4096] = {0};
    int bytes = recv(client, buffer, sizeof(buffer), 0);
    if (bytes <= 0) return "";
    return string(buffer, bytes);
}

void handleClient(int client) {
    string request = readRequest(client);
    if (request.empty()) return;
    
    // Получаем метод и путь
    istringstream ss(request);
    string method, path;
    ss >> method >> path;
    
    // GitHub callback
    if (path.find("/auth/github/callback?code=") == 0) {
        string code = path.substr(28);
        string result = Auth::githubAuth(code);
        
        string html = R"(<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Успешная авторизация</title>
    <style>
        body { padding: 40px; font-family: Arial; text-align: center; }
        pre { background: #f0f0f0; padding: 20px; margin: 20px; border-radius: 5px; }
    </style>
</head>
<body>
    <h2>✅ Авторизация прошла успешно!</h2>
    <pre>)" + result + R"(</pre>
    <p><a href="/">Вернуться на главную</a></p>
</body>
</html>)";
        
        sendResponse(client, html);
        return;
    }
    
    // Telegram API
    if (path == "/api/telegram" && method == "POST") {
        // Ищем тело запроса
        size_t body_start = request.find("\r\n\r\n");
        if (body_start != string::npos) {
            string body = request.substr(body_start + 4);
            
            // Парсим form-data
            string telegram_id, name;
            istringstream iss(body);
            string pair;
            
            while (getline(iss, pair, '&')) {
                size_t eq = pair.find('=');
                if (eq != string::npos) {
                    string key = pair.substr(0, eq);
                    string value = pair.substr(eq + 1);
                    
                    if (key == "telegram_id") telegram_id = value;
                    else if (key == "name") name = value;
                }
            }
            
            if (!telegram_id.empty() && !name.empty()) {
                string result = Auth::telegramAuth(telegram_id, name);
                sendResponse(client, result, true);
            } else {
                sendResponse(client, "{\"error\":\"Missing parameters\"}", true);
            }
        }
        return;
    }
    
    // Проверка токена
    if (path.find("/api/verify?token=") == 0) {
        string token = path.substr(18);
        string result = Auth::verifyToken(token);
        sendResponse(client, result, true);
        return;
    }
    
    // Главная страница
    sendResponse(client, Auth::homePage());
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
    
    cout << "🌐 Сервер запущен на порту " << port << endl;
    
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