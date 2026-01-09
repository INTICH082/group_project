async function createCourse() {
    try {
        const body = {
            Name: document.getElementById('course-name').value,
            Desc: document.getElementById('course-desc').value,
            TeacherID: parseInt(document.getElementById('course-teacher-id').value) || 0
        };
        const data = await apiCall('/teacher/course/create', 'POST', body);
        setResponse('create-course-response', data);
    } catch (e) { setResponse('create-course-response', e.message, true); }
}

async function enrollUser() {
    try {
        const data = await apiCall('/teacher/course/enroll', 'GET', null, {
            course_id: document.getElementById('enroll-course-id').value,
            user_id: document.getElementById('enroll-user-id').value
        });
        setResponse('enroll-response', data);
    } catch (e) { setResponse('enroll-response', e.message, true); }
}

async function deleteCourse() {
    try {
        const data = await apiCall('/teacher/course/delete', 'GET', null, { id: document.getElementById('delete-course-id').value });
        setResponse('delete-course-response', data);
    } catch (e) { setResponse('delete-course-response', e.message, true); }
}

async function createQuestion() {
    try {
        const body = {
            title: document.getElementById('q-title').value,
            text: document.getElementById('q-text').value,
            options: getListValues('q-options-list'),
            correct_option: parseInt(document.getElementById('q-correct').value)
        };
        const data = await apiCall('/teacher/question/create', 'POST', body);
        setResponse('create-q-response', data);
    } catch (e) { setResponse('create-q-response', e.message, true); }
}

async function updateQuestion() {
    try {
        const body = {
            id: parseInt(document.getElementById('update-q-id').value),
            text: document.getElementById('update-q-text').value,
            options: getListValues('update-q-options-list'),
            correct_option: parseInt(document.getElementById('update-q-correct').value)
        };
        const data = await apiCall('/teacher/question/update', 'POST', body);
        setResponse('update-q-response', data);
    } catch (e) { setResponse('update-q-response', e.message, true); }
}

async function deleteQuestion() {
    try {
        const data = await apiCall('/teacher/question/delete', 'GET', null, { id: document.getElementById('delete-q-id').value });
        setResponse('delete-q-response', data);
    } catch (e) { setResponse('delete-q-response', e.message, true); }
}

async function listAllQuestions() {
    try {
        const text = await apiCall('/teacher/question/list');
        const data = JSON.parse(text);
        renderQuestions(data, 'all-questions-list');
    } catch (e) {
        document.getElementById('all-questions-list').innerHTML = `<div class="response error">${e.message}</div>`;
    }
}

async function listCourseQuestions() {
    try {
        const text = await apiCall('/teacher/course/questions', 'GET', null, { course_id: document.getElementById('course-q-id').value });
        const data = JSON.parse(text);
        renderQuestions(data, 'course-questions-list');
    } catch (e) {
        document.getElementById('course-questions-list').innerHTML = `<div class="response error">${e.message}</div>`;
    }
}

async function createTest() {
    try {
        const body = {
            course_id: parseInt(document.getElementById('test-course-id').value),
            name: document.getElementById('test-name').value,
            question_ids: getListNumbers('test-q-ids-list')
        };
        const data = await apiCall('/teacher/test/create', 'POST', body);
        setResponse('create-test-response', data);
    } catch (e) { setResponse('create-test-response', e.message, true); }
}

async function updateTestStatus() {
    try {
        const data = await apiCall('/teacher/test/status', 'GET', null, {
            id: document.getElementById('status-test-id').value,
            active: document.getElementById('test-active').value
        });
        setResponse('status-test-response', data);
    } catch (e) { setResponse('status-test-response', e.message, true); }
}

async function reorderQuestions() {
    try {
        const body = {
            test_id: parseInt(document.getElementById('reorder-test-id').value),
            question_ids: getListNumbers('reorder-ids-list')
        };
        const data = await apiCall('/teacher/test/questions/reorder', 'POST', body);
        setResponse('reorder-response', data);
    } catch (e) { setResponse('reorder-response', e.message, true); }
}

async function listTestResults() {
    try {
        const text = await apiCall('/teacher/test/results', 'GET', null, { test_id: document.getElementById('results-test-id').value });
        const data = JSON.parse(text);
        document.getElementById('test-results').innerHTML = `<pre class="raw-json">${JSON.stringify(data, null, 2)}</pre>`;
        createJsonToggle(document.getElementById('test-results'), data);
    } catch (e) {
        document.getElementById('test-results').innerHTML = `<div class="response error">${e.message}</div>`;
    }
}

async function listCourseTests() {
    try {
        const text = await apiCall('/course/tests', 'GET', null, { course_id: document.getElementById('tests-course-id').value });
        const data = JSON.parse(text);
        renderTests(data, 'course-tests-list');
    } catch (e) {
        document.getElementById('course-tests-list').innerHTML = `<div class="response error">${e.message}</div>`;
    }
}