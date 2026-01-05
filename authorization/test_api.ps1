# Тестирование API
Write-Host "=== ТЕСТИРОВАНИЕ API ===" -ForegroundColor Cyan

# 1. Тест Telegram API
Write-Host "`n1. Тест Telegram API..." -ForegroundColor Yellow
$telegramTest = curl -s -X POST http://localhost:8081/api/telegram -d "telegram_id=123456" -d "name=Иван Иванов"
Write-Host "Результат: $telegramTest" -ForegroundColor Gray

# 2. Извлекаем токен из ответа
if ($telegramTest -match '"token":"([^"]+)"') {
    $token = $matches[1]
    Write-Host "Получен токен: $token" -ForegroundColor Green
    
    # 3. Тест проверки токена
    Write-Host "`n2. Тест проверки токена..." -ForegroundColor Yellow
    $verifyTest = curl -s "http://localhost:8081/api/verify?token=$token"
    Write-Host "Результат: $verifyTest" -ForegroundColor Gray
}

# 4. Тест главной страницы
Write-Host "`n3. Тест главной страницы..." -ForegroundColor Yellow
try {
    $page = Invoke-WebRequest -Uri "http://localhost:8081" -TimeoutSec 3
    Write-Host "✅ Главная страница работает" -ForegroundColor Green
} catch {
    Write-Host "❌ Главная страница недоступна" -ForegroundColor Red
}