@echo off
chcp 65001 > nul
title LocalLLMAPI - instalacja
cd /d "%~dp0"

echo ==============================================
echo   LocalLLMAPI - instalacja zaleznosci
echo ==============================================
echo.

echo [1/2] Zaleznosci Python (w tym tiktoken, wymagany przez serwer)...
pip install -r requirements.txt
if errorlevel 1 goto :blad

echo.
echo [2/2] llama-cpp-python z akceleracja Vulkan...
echo       Wymagane wczesniejsze zainstalowanie Vulkan SDK
echo       oraz kompilatora C++ (np. Visual Studio Build Tools).
set CMAKE_ARGS=-DGGML_VULKAN=on
pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir
if errorlevel 1 goto :blad

echo.
echo Gotowe. Uruchom start.bat.
pause
exit /b 0

:blad
echo.
echo Instalacja nie powiodla sie - patrz komunikaty powyzej.
pause
exit /b 1
