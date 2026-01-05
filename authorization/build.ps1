# build.ps1 - ИСПРАВЛЕННЫЙ
Write-Host "=== СБОРКА ПРОЕКТА ===" -ForegroundColor Green

# Проверяем компилятор
$gcc = "C:\msys64\ucrt64\bin\g++.exe"
if (-not (Test-Path $gcc)) {
    Write-Host "❌ Компилятор не найден" -ForegroundColor Red
    exit 1
}

# АБСОЛЮТНЫЕ ПУТИ для надежности
$project_root = "C:\Users\KSK-SHOP\projects\group_project\group_project"
$mysql_include = "$project_root\mysql-connector\include"
$mysql_lib = "$project_root\mysql-connector\lib"
$msys2_include = "C:\msys64\ucrt64\include"
$msys2_lib = "C:\msys64\ucrt64\lib"

Write-Host "`nПроверка путей:" -ForegroundColor Yellow

# Проверяем файлы
if (-not (Test-Path "$mysql_include\mysql.h")) {
    Write-Host "❌ mysql.h не найден по пути: $mysql_include\mysql.h" -ForegroundColor Red
    exit 1
} else {
    Write-Host "✅ mysql.h найден" -ForegroundColor Green
}

# Создаем папку build
if (Test-Path "build") {
    Remove-Item build -Recurse -Force
}
mkdir build
cd build

Write-Host "`nКомпиляция..." -ForegroundColor Yellow

# Компилируем все файлы с правильными путями
& $gcc -c "$project_root\authorization\database.cpp" -I"$project_root\authorization" -I"$mysql_include" -I"$msys2_include" -std=c++11
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка компиляции database.cpp" -ForegroundColor Red
    exit 1
}

& $gcc -c "$project_root\authorization\auth.cpp" -I"$project_root\authorization" -I"$mysql_include" -I"$msys2_include" -std=c++11
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка компиляции auth.cpp" -ForegroundColor Red
    exit 1
}

& $gcc -c "$project_root\authorization\server.cpp" -I"$project_root\authorization" -I"$mysql_include" -I"$msys2_include" -std=c++11
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка компиляции server.cpp" -ForegroundColor Red
    exit 1
}

& $gcc -c "$project_root\authorization\main.cpp" -I"$project_root\authorization" -I"$mysql_include" -I"$msys2_include" -std=c++11
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка компиляции main.cpp" -ForegroundColor Red
    exit 1
}

Write-Host "`nЛинковка..." -ForegroundColor Yellow

# Собираем исполняемый файл
& $gcc database.o auth.o server.o main.o -o auth.exe `
    -L"$mysql_lib" `
    -L"$msys2_lib" `
    -lws2_32 -llibmysql -lcurl 

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка линковки" -ForegroundColor Red
    Write-Host "Проверьте наличие библиотек в:" -ForegroundColor Yellow
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

Write-Host "`n🎉 Сборка завершена!" -ForegroundColor Green
Write-Host "Запуск: .\auth.exe" -ForegroundColor Cyan
Write-Host "Откройте: http://localhost:8081" -ForegroundColor Cyan

cd ..