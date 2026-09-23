@echo off
chcp 65001 >nul
title LaVera EV Telemetry Hub (Offline & Online Sync)
color 0b

echo ========================================================
echo        Iniciando LaVera EV Telemetry Hub Server
echo ========================================================
echo.

cd /d "%~dp0ev-telemetry-hub"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] No se ha encontrado Python en el sistema.
    echo Por favor instala Python 3.10 o superior desde https://www.python.org/
    pause
    exit /b 1
)

echo [*] Servidor listo.
echo [*] Abriendo panel de control en tu navegador (http://localhost:8088) ...
timeout /t 2 /nobreak >nul
start "" "http://localhost:8088"

echo.
echo Presiona Ctrl+C en esta ventana para detener el servidor cuando termines.
echo.
python all-in-one/app.py
pause
