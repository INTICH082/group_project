document.getElementById('loginForm').addEventListener('submit', async function(event) {
    event.preventDefault();

    const login = document.getElementById('login').value.trim();
    const password = document.getElementById('password').value;
    const errorMessage = document.getElementById('errorMessage');

    if (!login || !password) {
        errorMessage.textContent = 'Заполните все поля!';
        errorMessage.style.display = 'block';
        return;
    }

    errorMessage.style.display = 'none';

    try {
        // Шаг 1: Отправляем на API первого друга для получения JWT
        const response1 = await fetch('https://api-druha1.example.com/auth', {  // Замени на реальный URL API первого друга
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                login: login,
                password: password
            })
        });

        if (!response1.ok) {
            throw new Error(`Ошибка от API1: ${response1.status}`);
        }

        const data1 = await response1.json();
        const jwtToken = data1.token;  // Предполагаем, что токен в поле 'token'

        if (!jwtToken) {
            throw new Error('JWT токен не получен');
        }

        // Сохраняем JWT (временно, для теста — в реале используй secure cookies или не храни)
        localStorage.setItem('jwtToken', jwtToken);

        // Шаг 2: Переправляем JWT на API второго друга
        const response2 = await fetch('https://api-druha2.example.com/verify', {  // Замени на реальный URL API второго друга
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                // Альтернатива: 'Authorization': `Bearer ${jwtToken}` — если нужно в headers
            },
            body: JSON.stringify({
                token: jwtToken  // Отправляем токен в body
            })
        });

        if (!response2.ok) {
            throw new Error(`Ошибка от API2: ${response2.status}`);
        }

        const data2 = await response2.json();
        console.log('Ответ от второго API:', data2);  // Для дебага — что вернул второй друг

        // Если всё ок — сохраняем логин (как раньше) и переходим
        localStorage.setItem('username', login);
        localStorage.setItem('userPassword', password);  // Только для твоего профиля, не обязательно

        // Показываем уведомление
        document.getElementById('username').textContent = login;
        document.getElementById('toast').classList.add('show');

        // Переход на test.html
        setTimeout(() => {
            window.location.href = 'test.html';
        }, 1500);

    } catch (error) {
        console.error('Ошибка авторизации:', error);
        errorMessage.textContent = 'Ошибка: ' + error.message;
        errorMessage.style.display = 'block';
    }
});