# API модуля авторизации

## Эндпоинты

### 1. Старт OAuth процесса
**GET /auth?login_token={token}**
- `login_token` - токен сессии от Web Client/Bot Logic
- Возвращает: `{"auth_url": "URL", "state_token": "TOKEN"}`

### 2. Callback от провайдера (GitHub)
**GET /auth/callback?code={code}&state={state_token}**
- `code` - код от GitHub OAuth
- `state_token` - токен из предыдущего шага
- Возвращает JWT пару: `{"access_token": "...", "refresh_token": "...", "user_id": N, "expires_in": 900}`

### 3. Обновление токенов
**POST /auth/refresh**
- Тело: `refresh_token={token}`
- Возвращает новую пару токенов (формат как выше)

### 4. Проверка access token
**GET /auth/verify?token={access_token}**
- Возвращает: `{"valid": true/false, "user_id": N}`

### 5. Telegram авторизация (прямая)
**POST /api/telegram**
- Тело (form-data): `telegram_id=...&name=...`
- Возвращает JWT пару

### 6. Старый GitHub callback (для совместимости)
**GET /auth/github/callback?code={code}**
- Прямая авторизация через GitHub
- Возвращает HTML страницу с токенами