#define _HAS_STD_BYTE 0

#include "crow.h"         
#include "auth.h"
#include "database.h"
#include "utils.h"

#include <iostream>
#include <string>
#include <map>
#include <cstdlib>      // getenv
#include <exception>

using namespace std;

int main()
{
    cout << "1. Server started main()" << endl;

    try
    {
        const char* github_client_id     = getenv("GITHUB_CLIENT_ID");
        const char* github_client_secret = getenv("GITHUB_CLIENT_SECRET");
        const char* db_password          = getenv("DB_PASSWORD");
        const char* jwt_secret           = getenv("JWT_SECRET");

        cout << "2. Env variables read" << endl;
        cout << "GITHUB_CLIENT_ID:     " << (github_client_id     ? github_client_id     : "NOT SET") << endl;
        cout << "GITHUB_CLIENT_SECRET: " << (github_client_secret ? github_client_secret : "NOT SET") << endl;
        cout << "DB_PASSWORD:          " << (db_password          ? db_password          : "NOT SET") << endl;
        cout << "JWT_SECRET:           " << (jwt_secret           ? jwt_secret           : "NOT SET") << endl;

        if (!github_client_id || !github_client_secret || !db_password || !jwt_secret) {
            cerr << "Error: Missing one or more environment variables" << endl;
            return 1;
        }

        cout << "3. Creating Crow app..." << endl;
        crow::SimpleApp app;
        cout << "4. Crow app created" << endl;

        // Тестовый маршрут для проверки — открой http://localhost:8081/test
        CROW_ROUTE(app, "/test")
        ([](){
            return "Server is alive! Everything works.";
        });

        // Здесь должны быть твои основные маршруты (OAuth, auth и т.д.)
        // Пример:
        // CROW_ROUTE(app, "/auth/github")(...) 
        // CROW_ROUTE(app, "/auth/github/callback")(...)

        cout << "5. Routes registered" << endl;

        cout << "6. Starting server on port 8081..." << endl;
        app.port(8081).multithreaded().run();
        cout << "7. Server stopped (should not reach here)" << endl;
    }
    catch (const exception& e)
    {
        cerr << "Exception in main: " << e.what() << endl;
        return 1;
    }
    catch (...)
    {
        cerr << "Unknown exception in main" << endl;
        return 1;
    }

    cout << "8. main() finished" << endl;
    return 0;
}