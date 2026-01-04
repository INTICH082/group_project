document.getElementById('loginForm').addEventListener('submit', function(event) {
    event.preventDefault();

    const login = document.getElementById('login').value.trim();
    const password = document.getElementById('password').value;
    const errorMessage = document.getElementById('errorMessage');

    if (!login || !password) {
        errorMessage.style.display = 'block';
        return;
    }

    errorMessage.style.display = 'none';

    // Сохраняем данные
    localStorage.setItem('username', login);
    localStorage.setItem('userPassword', password);

    // Уведомление
    document.getElementById('username').textContent = login;
    document.getElementById('toast').classList.add('show');

    // Переход
    setTimeout(() => {
        window.location.href = 'test.html';
    }, 1500);
});