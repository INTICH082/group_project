async function healthCheck() {
    try {
        const data = await apiCall('/health');
        setResponse('health-response', data, false);
    } catch (e) {
        setResponse('health-response', e.message, true);
    }
}