const BASE_URL = "https://my-app-logic.onrender.com";
const token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3Njc2MjU1MzksInJvbGUiOiJzdHVkZW50IiwidXNlcl9pZCI6M30.mg9i-z0hgLpGvNycSQY_zKKPji2GvldMIOb3FZIsvcM";
const username = "Тестовый студент";

//if (!token || !username) {
    //alert('Нет авторизации! Перенаправляем на вход...');
  //  window.location.href = 'index.html';
//}

// Отображаем имя пользователя
document.getElementById('usernameDisplay').textContent = username;
document.getElementById('profileLogin').textContent = username;
document.getElementById('profileToken').textContent = token;

// Заголовки для всех запросов
const headers = {
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json"
};

let questions = [];  // Массив вопросов с сервера

// Загрузка вопросов
document.getElementById('loadQuestions').addEventListener('click', async () => {
    const courseId = document.getElementById('courseSelect').value;
    if (!courseId) {
        alert('Сначала выберите курс!');
        return;
    }

    try {
        const response = await fetch(`${BASE_URL}/course/${courseId}/questions`, {
            method: 'GET',
            headers: headers
        });

        if (!response.ok) {
            const err = await response.text();
            throw new Error(`Ошибка ${response.status}: ${err}`);
        }

        questions = await response.json();
        console.log('Вопросы получены:', questions);

        if (questions.length === 0) {
            document.getElementById('questionsContainer').innerHTML = '<p>В этом курсе пока нет вопросов.</p>';
            document.getElementById('submitAnswers').style.display = 'none';
            return;
        }

        renderQuestions(questions);
        document.getElementById('submitAnswers').style.display = 'block';
        document.getElementById('resultContainer').innerHTML = '';

    } catch (error) {
        console.error(error);
        alert('Не удалось загрузить вопросы: ' + error.message);
    }
});

// Отрисовка вопросов с вариантами (радиокнопки)
function renderQuestions(questions) {
    const container = document.getElementById('questionsContainer');
    container.innerHTML = '';

    questions.forEach((q, index) => {
        const block = document.createElement('div');
        block.className = 'question-block';
        block.innerHTML = `<p><strong>Вопрос ${index + 1}:</strong> ${q.text}</p>`;

        if (q.options && q.options.length > 0) {
            q.options.forEach((option, i) => {
                const label = document.createElement('label');
                label.style.display = 'block';
                label.style.margin = '8px 0';
                label.innerHTML = `
                    <input type="radio" name="question-${q.id}" value="${i}" required>
                    ${option}
                `;
                block.appendChild(label);
            });
        } else {
            // Если нет options — текстовый ответ
            const input = document.createElement('input');
            input.type = 'text';
            input.placeholder = 'Введите ответ';
            input.dataset.questionId = q.id;
            block.appendChild(input);
        }

        container.appendChild(block);
    });
}

// Отправка ответов
document.getElementById('submitAnswers').addEventListener('click', async () => {
    const answers = [];

    questions.forEach(q => {
        if (q.options) {
            // Радиокнопки — берём выбранный индекс
            const selected = document.querySelector(`input[name="question-${q.id}"]:checked`);
            if (selected) {
                answers.push({
                    question_id: q.id,
                    user_answer: parseInt(selected.value)  // индекс варианта (0, 1, 2...)
                });
            }
        } else {
            // Текстовый ввод
            const input = document.querySelector(`input[data-question-id="${q.id}"]`);
            if (input && input.value.trim()) {
                answers.push({
                    question_id: q.id,
                    user_answer: input.value.trim()
                });
            }
        }
    });

    if (answers.length === 0) {
        alert('Ответьте хотя бы на один вопрос!');
        return;
    }

    let correctCount = 0;
    let totalSent = 0;

    try {
        for (const ans of answers) {
            const response = await fetch(`${BASE_URL}/answer`, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify(ans)
            });

            if (!response.ok) {
                const err = await response.text();
                console.error('Ошибка на вопросе', ans.question_id, err);
                continue;
            }

            const result = await response.json();
            if (result.is_correct) correctCount++;
            totalSent++;
        }

        document.getElementById('resultContainer').innerHTML = `
            <p style="color: green;">Тест завершён!</p>
            <p>Правильных ответов: ${correctCount} из ${totalSent}</p>
        `;

    } catch (error) {
        console.error(error);
        alert('Ошибка при отправке ответов: ' + error.message);
    }
});

// Выход и профиль
document.getElementById('logoutBtn').addEventListener('click', () => {
    localStorage.clear();
    window.location.href = 'index.html';
});

document.getElementById('profileBtn').addEventListener('click', () => {
    document.getElementById('profileModal').style.display = 'flex';
});

document.getElementById('closeModal').addEventListener('click', () => {
    document.getElementById('profileModal').style.display = 'none';
});

window.addEventListener('click', (e) => {
    if (e.target === document.getElementById('profileModal')) {
        document.getElementById('profileModal').style.display = 'none';
    }
});