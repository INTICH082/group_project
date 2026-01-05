# build_final.ps1
Write-Host "=== СБОРКА ФИНАЛЬНОЙ ВЕРСИИ МОДУЛЯ АВТОРИЗАЦИИ ===" -ForegroundColor Green

# Проверяем компилятор
$gcc = "C:\msys64\ucrt64\bin\g++.exe"
if (-not (Test-Path $gcc)) {
    Write-Host "❌ Компилятор не найден" -ForegroundColor Red
    exit 1
}

# Абсолютные пути
$project_root = "C:\Users\KSK-SHOP\projects\group_project\group_project"
$auth_dir = "$project_root\authorization"
$mysql_include = "$project_root\mysql-connector\include"
$mysql_lib = "$project_root\mysql-connector\lib"
$msys2_include = "C:\msys64\ucrt64\include"
$msys2_lib = "C:\msys64\ucrt64\lib"

Write-Host "`nПроверка файлов..." -ForegroundColor Yellow

# Проверяем файлы
$files = @(
    "$auth_dir\auth.h",
    "$auth_dir\auth.cpp",
    "$auth_dir\database.h", 
    "$auth_dir\database.cpp",
    "$auth_dir\server.h",
    "$auth_dir\server.cpp",
    "$auth_dir\main.cpp",
    "$auth_dir\config.h"
)

foreach ($file in $files) {
    if (-not (Test-Path $file)) {
        Write-Host "❌ Файл не найден: $file" -ForegroundColor Red
        exit 1
    }
}

Write-Host "✅ Все файлы на месте" -ForegroundColor Green

# Создаем папку build
if (Test-Path "build") {
    Write-Host "`nОчистка предыдущей сборки..." -ForegroundColor Yellow
    Remove-Item build -Recurse -Force
}
mkdir build
cd build

Write-Host "`nКомпиляция..." -ForegroundColor Yellow

# Компилируем все файлы
$compile_cmd = @(
    "-c", "$auth_dir\database.cpp",
    "-I", "$auth_dir",
    "-I", "$mysql_include", 
    "-I", "$msys2_include",
    "-std=c++11",
    "-Wall"
)

& $gcc @compile_cmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка компиляции database.cpp" -ForegroundColor Red
    exit 1
}

& $gcc -c "$auth_dir\auth.cpp" -I"$auth_dir" -I"$mysql_include" -I"$msys2_include" -std=c++11 -Wall
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка компиляции auth.cpp" -ForegroundColor Red
    exit 1
}

& $gcc -c "$auth_dir\server.cpp" -I"$auth_dir" -I"$mysql_include" -I"$msys2_include" -std=c++11 -Wall
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка компиляции server.cpp" -ForegroundColor Red
    exit 1
}

& $gcc -c "$auth_dir\main.cpp" -I"$auth_dir" -I"$mysql_include" -I"$msys2_include" -std=c++11 -Wall
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка компиляции main.cpp" -ForegroundColor Red
    exit 1
}

Write-Host "`nЛинковка..." -ForegroundColor Yellow

# Собираем исполняемый файл
& $gcc database.o auth.o server.o main.o -o auth_module.exe `
    -L"$mysql_lib" `
    -L"$msys2_lib" `
    -lws2_32 -llibmysql -lcurl 

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка линковки" -ForegroundColor Red
    Write-Host "Проверьте наличие библиотек:" -ForegroundColor Yellow
    Write-Host "1. $mysql_lib\libmysql.dll" -ForegroundColor Yellow
    Write-Host "2. C:\msys64\ucrt64\bin\libcurl-4.dll" -ForegroundColor Yellow
    exit 1
}

# Копируем необходимые DLL
Write-Host "`nКопирование DLL..." -ForegroundColor Yellow

$dlls = @(
    @("$mysql_lib\libmysql.dll", "libmysql.dll"),
    @("C:\msys64\ucrt64\bin\libcurl-4.dll", "libcurl-4.dll")
)

foreach ($dll in $dlls) {
    $source, $name = $dll
    if (Test-Path $source) {
        Copy-Item $source .
        Write-Host "✅ $name" -ForegroundColor Green
    } else {
        Write-Host "⚠️  $name не найден (может работать и без него)" -ForegroundColor Yellow
    }
}

Write-Host "`n🎉 Сборка завершена успешно!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Запуск модуля: .\auth_module.exe" -ForegroundColor Cyan
Write-Host "URL для тестирования: http://localhost:8081" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "`nДля интеграции с другими модулями:" -ForegroundColor Yellow
Write-Host "1. Другие модули должны отправлять запросы к вышеуказанному URL" -ForegroundColor Gray
Write-Host "2. Все ответы в формате JSON" -ForegroundColor Gray
Write-Host "3. Нет HTML-страниц - чистый API" -ForegroundColor Gray

cd ..