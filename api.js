const BASE_URL = 'https://my-app-logic.onrender.com';
let token = '';

async function apiCall(endpoint, method = 'GET', body = null, query = {}) {
    if (!window.serverAwake) {
        try { await fetch(BASE_URL + '/health'); } catch {}
        window.serverAwake = true;
    }

    const url = new URL(BASE_URL + endpoint);
    Object.keys(query).forEach(k => url.searchParams.append(k, query[k]));

    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = token;

    const res = await fetch(url, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const text = await res.text();

    if (!res.ok) throw new Error(`Ошибка ${res.status}: ${text || res.statusText}`);
    return text;
}