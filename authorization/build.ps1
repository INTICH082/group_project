# Простая сборка
Write-Host "=== СБОРКА ПРОЕКТА ===" -ForegroundColor Green

# Проверяем компилятор
$gcc = "C:\msys64\ucrt64\bin\g++.exe"
if (-not (Test-Path $gcc)) {
    Write-Host "❌ Компилятор не найден" -ForegroundColor Red
    Write-Host "Установите: pacman -S mingw-w64-ucrt-x86_64-gcc" -ForegroundColor Yellow
    exit 1
}

# Создаем папку build
if (Test-Path "build") {
    Remove-Item build -Recurse -Force
}
mkdir build
cd build

Write-Host "Компиляция..." -ForegroundColor Yellow

# Компилируем все файлы
& $gcc -c ..\database.cpp -I.. -I..\..\mysql-connector\include -I"C:\msys64\ucrt64\include" -std=c++11
& $gcc -c ..\auth.cpp -I.. -I..\..\mysql-connector\include -I"C:\msys64\ucrt64\include" -std=c++11
& $gcc -c ..\server.cpp -I.. -I..\..\mysql-connector\include -I"C:\msys64\ucrt64\include" -std=c++11
& $gcc -c ..\main.cpp -I.. -I..\..\mysql-connector\include -I"C:\msys64\ucrt64\include" -std=c++11

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка компиляции" -ForegroundColor Red
    exit 1
}

Write-Host "Линковка..." -ForegroundColor Yellow

# Собираем исполняемый файл
& $gcc database.o auth.o server.o main.o -o auth.exe `
    -L..\..\mysql-connector\lib `
    -L"C:\msys64\ucrt64\lib" `
    -lws2_32 -llibmysql -lcurl -lssl -lcrypto

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка линковки" -ForegroundColor Red
    exit 1
}

# Копируем необходимые DLL
Write-Host "Копирование DLL..." -ForegroundColor Yellow

$dlls = @(
    @("..\..\mysql-connector\lib\libmysql.dll", "libmysql.dll"),
    @("C:\msys64\ucrt64\bin\libcurl-4.dll", "libcurl-4.dll")
)

foreach ($dll in $dlls) {
    $source, $name = $dll
    if (Test-Path $source) {
        Copy-Item $source .
        Write-Host "✅ $name" -ForegroundColor Green
    } else {
        Write-Host "⚠️  $name не найден" -ForegroundColor Yellow
    }
}

Write-Host "`n🎉 Сборка завершена!" -ForegroundColor Green
Write-Host "Запуск: .\auth.exe" -ForegroundColor Cyan
Write-Host "Откройте: http://localhost:8081" -ForegroundColor Cyan

cd ..