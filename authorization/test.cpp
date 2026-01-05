#include <iostream>
#include <curl/curl.h>

using namespace std;

size_t writeCallback(void* contents, size_t size, size_t nmemb, string* data) {
    data->append((char*)contents, size * nmemb);
    return size * nmemb;
}

string sendRequest(const string& url, const string& post_data) {
    CURL* curl = curl_easy_init();
    string response;
    
    if (curl) {
        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_data.c_str());
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
        
        curl_easy_perform(curl);
        curl_easy_cleanup(curl);
    }
    
    return response;
}

int main() {
    cout << "Тестирование API авторизации\n\n";
    
    // Регистрация
    cout << "1. Регистрация:\n";
    string reg_data = "fullname=Тест%20Пользователь&email=test@example.com&course=3&password=test123";
    string reg_resp = sendRequest("http://localhost:8080/api/register", reg_data);
    cout << "Ответ: " << reg_resp << "\n\n";
    
    // Вход
    cout << "2. Вход:\n";
    string login_data = "email=test@example.com&password=test123";
    string login_resp = sendRequest("http://localhost:8080/api/login", login_data);
    cout << "Ответ: " << login_resp << "\n\n";
    
    // Телеграм (пример)
    cout << "3. Телеграм авторизация:\n";
    string tg_data = "telegram_id=123456789&first_name=Иван&last_name=Иванов";
    string tg_resp = sendRequest("http://localhost:8080/api/telegram", tg_data);
    cout << "Ответ: " << tg_resp << endl;
    
    return 0;
}