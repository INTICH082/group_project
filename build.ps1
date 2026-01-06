Write-Host "=== Сборка модуля авторизации ==="

$gcc = "C:\msys64\ucrt64\bin\g++.exe"
$project = "C:\Users\KSK-SHOP\projects\group_project\group_project"
$mysql_inc = "$project\mysql-connector\include"
$mysql_lib = "$project\mysql-connector\lib"

mkdir -Force build
cd build

# Компиляция для Windows
& $gcc -c "$project\authorization\database.cpp" -I"$project\authorization" -I"$mysql_inc" -std=c++11
& $gcc -c "$project\authorization\auth.cpp" -I"$project\authorization" -I"$mysql_inc" -std=c++11
& $gcc -c "$project\authorization\server.cpp" -I"$project\authorization" -I"$mysql_inc" -std=c++11
& $gcc -c "$project\authorization\main.cpp" -I"$project\authorization" -I"$mysql_inc" -std=c++11

# Линковка с Windows библиотеками
& $gcc database.o auth.o server.o main.o -o auth_module.exe -L"$mysql_lib" -lws2_32 -llibmysql -lcurl

# Копируем DLL
Copy-Item "$mysql_lib\libmysql.dll" .
Copy-Item "C:\msys64\ucrt64\bin\libcurl-4.dll" .

Write-Host "`n✅ Сборка завершена!"
Write-Host "Запуск: .\auth_module.exe"

cd ..