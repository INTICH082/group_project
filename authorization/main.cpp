#include "auth.h"
#include "server.h"
#include "config.h"
#include <iostream>
using namespace std;

int main() {
    cout << "🚀 Запуск сервера авторизации" << endl;
    
    if (!Auth::init()) {
        cerr << "❌ Ошибка инициализации" << endl;
        return 1;
    }
    
    cout << "✅ Все системы готовы" << endl;
    cout << "🌐 Адрес: http://localhost:" << Config::PORT << endl;
    cout << "🔗 GitHub OAuth активен" << endl;
    cout << "🤖 Telegram API: POST /api/telegram" << endl;
    cout << "🔍 Проверка токенов: GET /api/verify?token=..." << endl;
    
    HttpServer::start(Config::PORT);
    
    Auth::cleanup();
    return 0;
}