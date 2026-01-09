// Глобальные переменные для прохождения теста
let currentAttemptId = null;
let currentQuestions = [];
let currentIndex = 0;
let selectedAnswers = {};

// === Прохождение теста ===

async function loadCoursesForTest() {
    try {
        const text = await apiCall('/courses');
        const data = JSON.parse(text);
        renderCourses(data, 'test-courses-list', true);
    } catch (e) {
        document.getElementById('test-courses-list').innerHTML = `<div class="response error">${e.message}</div>`;
    }
}

async function loadTestsForCourse(courseId) {
    try {
        const text = await apiCall('/course/tests', 'GET', null, { course_id: courseId });
        const data = JSON.parse(text);
        renderTests(data, 'test-list');

        document.getElementById('step-course').classList.remove('active');
        document.getElementById('step-test').classList.add('active');
    } catch (e) {
        alert('Ошибка загрузки тестов: ' + e.message);
    }
}

async function startSelectedTest(testId) {
    try {
        const startData = await apiCall('/test/start', 'GET', null, { test_id: testId });
        const startRes = JSON.parse(startData);
        currentAttemptId = startRes.attempt_id;

        const fullTestText = await apiCall('/test/get', 'GET', null, { id: testId });
        const fullTest = JSON.parse(fullTestText);
        currentQuestions = fullTest.test?.questions || fullTest.questions || [];
        currentIndex = 0;
        selectedAnswers = {};

        document.getElementById('step-test').classList.remove('active');
        document.getElementById('step-quiz').classList.add('active');

        showQuestion();
    } catch (e) {
        alert('Не удалось начать тест: ' + e.message);
    }
}

function showQuestion() {
    if (currentIndex >= currentQuestions.length) {
        finishQuiz();
        return;
    }

    const q = currentQuestions[currentIndex];
    const block = document.getElementById('current-question');
    block.innerHTML = `<h3>${q.text || 'Без текста'}</h3><div style="margin-top: 20px;"></div>`;

    (q.options || []).forEach((opt, i) => {
        const label = document.createElement('label');
        label.className = 'radio-option';
        label.innerHTML = `
            <input type="radio" name="q${q.id}" value="${i}" ${selectedAnswers[q.id] === i ? 'checked' : ''}>
            ${opt}
        `;
        block.appendChild(label);
    });

    document.getElementById('quiz-progress').textContent = `Вопрос ${currentIndex + 1} из ${currentQuestions.length}`;
    document.getElementById('next-btn').textContent = currentIndex === currentQuestions.length - 1 ? 'Завершить тест' : 'Далее';
}

function nextQuestion() {
    const q = currentQuestions[currentIndex];
    const selected = document.querySelector(`input[name="q${q.id}"]:checked`);
    if (selected) {
        const option = parseInt(selected.value);
        selectedAnswers[q.id] = option;
        submitAnswerIfNeeded(q.id, option);
    } else if (currentQuestions.length > 1) {
        if (!confirm('Вы не выбрали ответ. Перейти к следующему?')) return;
    }

    currentIndex++;
    showQuestion();
}

async function submitAnswerIfNeeded(questionId, option) {
    if (currentAttemptId && option !== undefined) {
        try {
            await apiCall('/test/answer', 'POST', {
                attempt_id: currentAttemptId,
                question_id: questionId,
                selected_option: option
            });
        } catch (e) {
            console.error('Ошибка отправки ответа:', e);
        }
    }
}

async function finishQuiz() {
    if (currentAttemptId) {
        try {
            const data = await apiCall('/test/finish', 'GET', null, { attempt_id: currentAttemptId });
            const result = JSON.parse(data);
            document.getElementById('quiz-result').innerHTML = `
                Тест завершён!<br>
                Оценка: ${result.score || 'неизвестно'}
            `;
            createJsonToggle(document.getElementById('quiz-result'), result);
        } catch (e) {
            document.getElementById('quiz-result').textContent = 'Ошибка завершения: ' + e.message;
            document.getElementById('quiz-result').classList.replace('success', 'error');
        }
    }

    document.getElementById('step-quiz').classList.remove('active');
    document.getElementById('step-result').classList.add('active');
}

function restartTestFlow() {
    document.querySelectorAll('.test-step').forEach(s => s.classList.remove('active'));
    document.getElementById('step-course').classList.add('active');
    clearPrettyList('test-courses-list');
    clearPrettyList('test-list');
    document.getElementById('current-question').innerHTML = '';
    document.getElementById('quiz-result').innerHTML = '';
    currentAttemptId = null;
    currentQuestions = [];
    currentIndex = 0;
    selectedAnswers = {};
}