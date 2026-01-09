const SECRET = 'iplaygodotandclaimfun';

function generateToken() {
    const header = { alg: 'HS256', typ: 'JWT' };
    const now = Math.floor(Date.now() / 1000);
    const payload = {
        user_id: 1,
        exp: now + 7200,
        perms: ["user:block:write","user:fullName:write","course:add","course:user:add","course:del","quest:create","quest:update","quest:del","quest:read","course:test:add","course:test:write","course:read","test:quest:update","test:answer:read","course:test:view"],
        permissions: ["user:block:write","user:fullName:write","course:add","course:user:add","course:del","quest:create","quest:update","quest:del","quest:read","course:test:add","course:test:write","course:read","test:quest:update","test:answer:read","course:test:view"]
    };

    const encHeader = btoa(JSON.stringify(header)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const encPayload = btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const unsigned = `${encHeader}.${encPayload}`;
    const signature = CryptoJS.HmacSHA256(unsigned, SECRET).toString(CryptoJS.enc.Base64)
        .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

    token = `Bearer ${unsigned}.${signature}`;
    document.getElementById('token-input').value = token;
    setResponse('auth-response', 'Токен успешно сгенерирован!', false);
}

function saveToken() {
    token = document.getElementById('token-input').value.trim();
    setResponse('auth-response', 'Токен сохранён.', false);
}