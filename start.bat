@echo off
chcp 65001 > nul
setlocal
title LocalLLMAPI
cd /d "%~dp0"

echo ==============================================
echo   LocalLLMAPI  -  lokalny router OpenAI
echo ==============================================
echo.
echo   1. Uruchom serwer i otworz panel w przegladarce
echo   2. Uruchom sam serwer (bez przegladarki)
echo.
set /p wybor="Wybierz (1-2): "

if "%wybor%"=="2" goto server

echo.
echo Uruchamianie serwera na porcie 1000...
start "LocalLLMAPI Server" /B python -m uvicorn backend.router_server:app --host 0.0.0.0 --port 1000
timeout /t 2 /nobreak > nul
start http://localhost:1000
echo Panel:      http://localhost:1000
echo API:        http://localhost:1000/v1
echo.
echo Aby zatrzymac serwer zamknij okno "LocalLLMAPI Server".
pause
exit /b

:server
echo Uruchamianie serwera na porcie 1000 (Ctrl+C konczy)...
python -m uvicorn backend.router_server:app --host 0.0.0.0 --port 1000
