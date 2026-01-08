@echo off
echo ======================================
echo Telegram Bot Test System - Windows
echo ======================================
echo.

echo 1. Checking Docker...
docker --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not installed or not running!
    echo Please install Docker Desktop from: https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

echo 2. Building Docker images...
docker-compose build

echo.
echo 3. Starting containers...
docker-compose up -d

echo.
echo 4. Showing logs (Ctrl+C to exit)...
docker-compose logs -f

echo.
echo Commands:
echo - Stop: docker-compose down
echo - View logs: docker-compose logs -f
echo - Rebuild: docker-compose up -d --build
echo - Shell: docker-compose exec telegram-bot sh
echo.
pause