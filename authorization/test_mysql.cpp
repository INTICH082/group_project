#include <mysql.h>
#include <iostream>
using namespace std;

int main() {
    cout << "Проверка MySQL..." << endl;
    MYSQL* conn = mysql_init(nullptr);
    if (conn) {
        cout << "✅ MySQL инициализирован" << endl;
        mysql_close(conn);
    } else {
        cout << "❌ Ошибка инициализации MySQL" << endl;
    }
    return 0;
}