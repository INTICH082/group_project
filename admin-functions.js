async function blockUser() {
    try {
        const data = await apiCall('/admin/user/block', 'GET', null, {
            id: document.getElementById('block-user-id').value,
            block: document.getElementById('block-status').value
        });
        setResponse('block-response', data);
    } catch (e) { setResponse('block-response', e.message, true); }
}

async function updateName() {
    try {
        const data = await apiCall('/user/update-name', 'GET', null, {
            id: document.getElementById('name-user-id').value,
            name: document.getElementById('new-name').value
        });
        setResponse('name-response', data);
    } catch (e) { setResponse('name-response', e.message, true); }
}