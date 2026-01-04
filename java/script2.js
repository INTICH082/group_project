// Проверяем, авторизован ли пользователь
const username = localStorage.getItem('username');
const userPassword = localStorage.getItem('userPassword');

if (!username) {
    window.location.href = 'index.html';
}

// Приветствие
document.getElementById('welcomeText').textContent = `Добро пожаловать, ${username}!`;

// Заполняем модалку профиля
document.getElementById('profileLogin').textContent = username;
document.getElementById('profilePassword').textContent = userPassword || '(неизвестно)';

// Открытие профиля
document.getElementById('profileBtn').addEventListener('click', () => {
    document.getElementById('profileModal').style.display = 'flex';
});

// Закрытие модалки
document.getElementById('closeModal').addEventListener('click', () => {
    document.getElementById('profileModal').style.display = 'none';
});

window.addEventListener('click', (event) => {
    const modal = document.getElementById('profileModal');
    if (event.target === modal) {
        modal.style.display = 'none';
    }
});
 const jwtToken = localStorage.getItem('jwtToken');
if (!jwtToken) {
    window.location.href = 'index.html';  // Если нет токена — на вход
}

// В профиле добавь отображение токена (для дебага)
document.getElementById('profileRole').insertAdjacentHTML('afterend', `<p><strong>JWT Токен:</strong> ${jwtToken}</p>`);
// Выход
document.getElementById('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem('username');
    localStorage.removeItem('userPassword');
    window.location.href = 'index.html';
});

// Кнопка "Пройти тест" → переход на quiz.html
document.getElementById('startTest').addEventListener('click', function() {
    window.location.href = 'quiz.html';
});