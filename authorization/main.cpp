#include "auth.h"
#include "server.h"
#include "config.h"
#include <iostream>

using namespace std;

int main() {
    cout << "Запуск модуля авторизации..." << endl;
    
    if (!Auth::init()) {
        cerr << "Ошибка инициализации" << endl;
        return 1;
    }
    
    cout << "✅ Модуль готов к работе" << endl;
    HttpServer::start(Config::PORT);
    Auth::cleanup();
    
    return 0;
}