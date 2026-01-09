async function listCourses() {
    try {
        const text = await apiCall('/courses');
        const data = JSON.parse(text);
        renderCourses(data);
    } catch (e) {
        document.getElementById('courses-list').innerHTML = `<div class="response error">${e.message}</div>`;
    }
}