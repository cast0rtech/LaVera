@echo off
timeout /t 5 /nobreak >nul
cd /d "%~dp0"

:: Check if Docker daemon is responsive
docker info >nul 2>nul
if %errorlevel% equ 0 (
    echo [*] Docker disponible. Iniciando contenedor All-in-One...
    docker compose -f docker-compose.all-in-one.yml up -d
) else (
    echo [*] Docker no disponible. Iniciando servidor nativo de Python...
    start "" /b python all-in-one/app.py
)
