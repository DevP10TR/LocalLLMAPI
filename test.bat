@echo off
chcp 65001 > nul
echo ==============================================
echo   TESTOWANIE MODELU - LocalLLMAPI
echo ==============================================
echo.

set /p API_KEY="Klucz API (skopiuj z zakladki Klucze API): "
if "%API_KEY%"=="" exit /b
set /p MODEL="Nazwa modelu (z zakladki Modele): "
if "%MODEL%"=="" exit /b

echo.
echo Wysylam zapytanie testowe...
echo (Przy pierwszym uzyciu modelu moze to trwac 10-60 s - trwa wczytanie wag.)
echo.

curl.exe -N -X POST http://127.0.0.1:1000/v1/chat/completions ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer %API_KEY%" ^
  -d "{\"model\": \"%MODEL%\", \"messages\": [{\"role\": \"user\", \"content\": \"Napisz krotko: wszystko dziala\"}], \"stream\": true}"

echo.
echo.
echo Gotowe. Sprawdz statystyki na http://localhost:1000 (zakladka Home).
pause
