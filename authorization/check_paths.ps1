# check_paths.ps1
Write-Host "=== ПРОВЕРКА ПУТЕЙ ===" -ForegroundColor Green

$mysql_path = "..\..\mysql-connector\include"

Write-Host "`n1. Проверка папки MySQL Connector:" -ForegroundColor Yellow
if (Test-Path $mysql_path) {
    Write-Host "   ✅ Папка существует: $mysql_path" -ForegroundColor Green
    
    # Ищем mysql.h
    $mysql_h = Get-ChildItem -Path $mysql_path -Recurse -Filter "mysql.h" | Select-Object -First 1
    if ($mysql_h) {
        Write-Host "   ✅ mysql.h найден: $($mysql_h.FullName)" -ForegroundColor Green
        Write-Host "   Относительный путь от authorization/: $($mysql_h.FullName | Resolve-Path -Relative)" -ForegroundColor Cyan
    } else {
        Write-Host "   ❌ mysql.h не найден в $mysql_path" -ForegroundColor Red
        Write-Host "   Содержимое папки:" -ForegroundColor Yellow
        Get-ChildItem $mysql_path | ForEach-Object { Write-Host "   - $($_.Name)" }
    }
} else {
    Write-Host "   ❌ Папка не существует: $mysql_path" -ForegroundColor Red
}

Write-Host "`n2. Проверка компилятора:" -ForegroundColor Yellow
$gcc = "C:\msys64\ucrt64\bin\g++.exe"
if (Test-Path $gcc) {
    Write-Host "   ✅ GCC найден" -ForegroundColor Green
} else {
    Write-Host "   ❌ GCC не найден" -ForegroundColor Red
}

Write-Host "`n3. Тестовая компиляция с разными путями:" -ForegroundColor Yellow

# Создаем тестовый файл
@'
#include <iostream>
int main() { std::cout << "Test\n"; return 0; }
'@ | Out-File "test.cpp" -Encoding UTF8

# Пробуем разные пути
$test_paths = @(
    "..\..\mysql-connector\include",
    "..\..\mysql-connector\include\mysql",
    "C:\Program Files\MySQL\Connector C++ 8.0\include",
    "C:\Program Files (x86)\MySQL\Connector C++ 8.0\include"
)

foreach ($path in $test_paths) {
    if (Test-Path $path) {
        Write-Host "   Проверяем путь: $path" -ForegroundColor Gray
        & $gcc test.cpp -I$path -o test.exe 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   ✅ Компиляция успешна с $path" -ForegroundColor Green
        }
    }
}

Remove-Item test.cpp -ErrorAction SilentlyContinue
Remove-Item test.exe -ErrorAction SilentlyContinue