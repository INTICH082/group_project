function openTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');
    document.querySelector(`.tab-button[onclick="openTab('${tabName}')"]`).classList.add('active');
}

function setResponse(id, text, isError = false) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = text;
        el.classList.toggle('success', !isError);
        el.classList.toggle('error', isError);
    }
}

function createJsonToggle(container, rawData) {
    const toggle = document.createElement('div');
    toggle.className = 'json-toggle';
    toggle.textContent = 'Показать сырой JSON';
    toggle.onclick = () => {
        const existing = toggle.nextElementSibling;
        if (existing && existing.className === 'raw-json') {
            existing.remove();
            toggle.textContent = 'Показать сырой JSON';
        } else {
            const pre = document.createElement('pre');
            pre.className = 'raw-json';
            pre.textContent = JSON.stringify(rawData, null, 2);
            toggle.after(pre);
            toggle.textContent = 'Скрыть JSON';
        }
    };
    container.appendChild(toggle);
}

function clearPrettyList(id) {
    const container = document.getElementById(id);
    if (container) container.innerHTML = '';
}

function renderCourses(data, containerId = 'courses-list', clickable = false) {
    clearPrettyList(containerId);
    const container = document.getElementById(containerId);
    const courses = Array.isArray(data) ? data : (data.courses || []);
    if (courses.length === 0) {
        container.innerHTML = '<p style="color:#666;">Курсов нет.</p>';
        createJsonToggle(container, data);
        return;
    }
    courses.forEach(c => {
        const card = document.createElement('div');
        card.className = 'course-card';
        if (clickable) {
            card.style.cursor = 'pointer';
            card.onclick = () => loadTestsForCourse(c.id);
        }
        card.innerHTML = `
            <h4>${c.name || 'Без названия'}</h4>
            <p><strong>ID:</strong> ${c.id}</p>
            <p><strong>Описание:</strong> ${c.description ? c.description : 'Нет описания'}</p>
        `;
        container.appendChild(card);
    });
    createJsonToggle(container, data);
}

// Адаптировано под ваш API: плоский массив без active и question_ids
function renderTests(data, containerId) {
    clearPrettyList(containerId);
    const container = document.getElementById(containerId);
    const tests = Array.isArray(data) ? data : [];

    if (tests.length === 0) {
        container.innerHTML = '<p style="color:#666;">Тестов в этом курсе нет.</p>';
        createJsonToggle(container, data);
        return;
    }

    tests.forEach(t => {
        const card = document.createElement('div');
        card.className = 'test-card';
        card.style.cursor = 'pointer';
        card.onclick = () => startSelectedTest(t.id, t.name || 'Без названия');
        card.innerHTML = `
            <h4>${t.name || 'Без названия'}</h4>
            <p><strong>ID:</strong> ${t.id}</p>
        `;
        container.appendChild(card);
    });
    createJsonToggle(container, data);
}

function renderQuestions(data, containerId) {
    clearPrettyList(containerId);
    const container = document.getElementById(containerId);
    const questions = Array.isArray(data) ? data : (data.questions || []);
    if (questions.length === 0) {
        container.innerHTML = '<p style="color:#666;">Вопросов нет.</p>';
        createJsonToggle(container, data);
        return;
    }
    questions.forEach(q => {
        const card = document.createElement('div');
        card.className = 'question-card';
        let optionsHtml = '<ul class="options-list">';
        (q.options || []).forEach((opt, i) => {
            const isCorrect = i === q.correct_option;
            optionsHtml += `<li${isCorrect ? ' class="correct-option"' : ''}>${opt}</li>`;
        });
        optionsHtml += '</ul>';
        card.innerHTML = `
            <h4>${q.title || 'Без заголовка'}</h4>
            <p><strong>ID:</strong> ${q.id}</p>
            <p><strong>Текст:</strong> ${q.text || ''}</p>
            ${optionsHtml}
        `;
        container.appendChild(card);
    });
    createJsonToggle(container, data);
}

function addOption(listId) {
    const list = document.getElementById(listId);
    const div = document.createElement('div');
    div.className = 'item';
    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'Вариант ответа';
    const btn = document.createElement('button');
    btn.textContent = '✕';
    btn.onclick = () => div.remove();
    div.appendChild(input);
    div.appendChild(btn);
    list.appendChild(div);
}

function addId(listId) {
    const list = document.getElementById(listId);
    const div = document.createElement('div');
    div.className = 'item';
    const input = document.createElement('input');
    input.type = 'number';
    input.placeholder = 'ID';
    const btn = document.createElement('button');
    btn.textContent = '✕';
    btn.onclick = () => div.remove();
    div.appendChild(input);
    div.appendChild(btn);
    list.appendChild(div);
}

function getListValues(id) {
    return Array.from(document.querySelectorAll(`#${id} .item input`))
        .map(i => i.value.trim())
        .filter(v => v !== '');
}

function getListNumbers(id) {
    return Array.from(document.querySelectorAll(`#${id} .item input`))
        .map(i => parseInt(i.value))
        .filter(n => !isNaN(n));
}