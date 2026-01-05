#include "server.h"
#include "auth.h"
#include "config.h"
#include <winsock2.h>
#include <ws2tcpip.h>
#include <iostream>
#include <sstream>
#include "database.h"
using namespace std;

#pragma comment(lib, "ws2_32.lib")

// Прототипы вспомогательных функций
string getGitHubToken(const string& code);
string getGitHubUser(const string& token);
string parseJson(const string& json, const string& key);

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
    
    cout << "Запрос: " << method << " " << path << endl;
    
    // ========== ГЛАВНАЯ СТРАНИЦА ==========
    if (path == "/") {
        sendResponse(client, Auth::homePage());
        return;
    }
    
    // ========== СТАРТ OAuth (для Web Client/Bot Logic) ==========
    if (path.find("/auth?login_token=") == 0) {
        string login_token = path.substr(18);
        string result = Auth::startOAuth(login_token);
        sendResponse(client, result, true);
        return;
    }
    
    // ========== CALLBACK от GitHub ==========
    if (path.find("/auth/callback?") == 0) {
        // Парсим параметры
        size_t code_pos = path.find("code=");
        size_t state_pos = path.find("&state=");
        
        if (code_pos != string::npos) {
            string code, state;
            
            if (state_pos != string::npos) {
                code = path.substr(code_pos + 5, state_pos - (code_pos + 5));
                state = path.substr(state_pos + 7);
            } else {
                code = path.substr(code_pos + 5);
                state = "";
            }
            
            string result = Auth::handleGitHubCallback(code, state);
            sendResponse(client, result, true);
        } else {
            sendResponse(client, "{\"error\":\"Missing code parameter\"}", true);
        }
        return;
    }
    
    // ========== ОБНОВЛЕНИЕ ТОКЕНА (POST) ==========
    if (path == "/auth/refresh" && method == "POST") {
        size_t body_start = request.find("\r\n\r\n");
        if (body_start != string::npos) {
            string body = request.substr(body_start + 4);
            
            // Парсим refresh_token из body
            string refresh_token;
            size_t token_pos = body.find("refresh_token=");
            if (token_pos != string::npos) {
                refresh_token = body.substr(token_pos + 13);
                // Убираем возможные & или конец строки
                size_t end_pos = refresh_token.find('&');
                if (end_pos != string::npos) {
                    refresh_token = refresh_token.substr(0, end_pos);
                }
            }
            
            if (!refresh_token.empty()) {
                string result = Auth::refreshToken(refresh_token);
                sendResponse(client, result, true);
            } else {
                sendResponse(client, "{\"error\":\"refresh_token required\"}", true);
            }
        }
        return;
    }
    
    // ========== ПРОВЕРКА ТОКЕНА ==========
    if (path.find("/auth/verify?token=") == 0) {
        string token = path.substr(20);
        string result = Auth::verifyToken(token);
        sendResponse(client, result, true);
        return;
    }
    
    // ========== TELEGRAM AUTH (старый метод) ==========
    if (path == "/api/telegram" && method == "POST") {
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
    
    // ========== СТАРЫЙ GITHUB CALLBACK (для обратной совместимости) ==========
    if (path.find("/auth/github/callback?code=") == 0) {
        string code = path.substr(28);
        // Используем старый метод
        string gh_token = Auth::getGitHubToken(code);
        if (gh_token.empty()) {
            sendResponse(client, "{\"error\":\"GitHub auth failed\"}", true);
            return;
        }
        
        string user_info = Auth::getGitHubUser(gh_token);
        string github_id = Auth::parseJson(user_info, "id");
        string login = Auth::parseJson(user_info, "login");
        string name = Auth::parseJson(user_info, "name");
        
        if (github_id.empty() || login.empty()) {
            sendResponse(client, "{\"error\":\"Invalid user info\"}", true);
            return;
        }
        
        if (name.empty()) name = login;
        
        int user_id = Database::getUserByGithubId(github_id);
        if (user_id == 0) {
            string email = login + "@github.user";
            user_id = Database::createUser(name, email, github_id, 0);
        }
        
        if (user_id == 0) {
            sendResponse(client, "{\"error\":\"Database error\"}", true);
            return;
        }
        
        // Генерируем новую JWT пару
        string result = Auth::generateTokenPair(user_id);
        
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
    
    // ========== ВСЕ ОСТАЛЬНЫЕ ЗАПРОСЫ ==========
    sendResponse(client, "{\"error\":\"Endpoint not found\"}", true);
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
    cout << "🆕 Новые эндпоинты:" << endl;
    cout << "   GET  /auth?login_token=TOKEN" << endl;
    cout << "   GET  /auth/callback?code=CODE&state=TOKEN" << endl;
    cout << "   POST /auth/refresh (тело: refresh_token=TOKEN)" << endl;
    cout << "   GET  /auth/verify?token=TOKEN" << endl;
    
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