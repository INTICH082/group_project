#include "auth.h"
#include "server.h"
#include "config.h"
#include <iostream>
#include <cstdlib>
using namespace std;

int main() {
    cout << "🚀 Запуск модуля авторизации..." << endl;
    
    if (!Auth::init()) {
        cerr << "❌ Ошибка инициализации модуля" << endl;
        return 1;
    }
    
    cout << "✅ Модуль авторизации инициализирован" << endl;
    
    try {
        HttpServer::start(Config::PORT);
    } catch (const exception& e) {
        cerr << "❌ Ошибка сервера: " << e.what() << endl;
    } catch (...) {
        cerr << "❌ Неизвестная ошибка сервера" << endl;
    }
    
    Auth::cleanup();
    cout << "👋 Модуль авторизации завершил работу" << endl;
    
    return 0;
}