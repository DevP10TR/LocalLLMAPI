@echo off
chcp 65001 > nul
echo ==============================================
echo TESTOWANIE MODELU - LOCAL LLM API
echo ==============================================

set /p API_KEY="Podaj swoj klucz API (skopiuj ze strony): "
set /p MODEL="Podaj nazwe modelu (np. gemma-3-4b-it_rai_1.7.1_npu_4K): "

echo.
echo Wysylam zapytanie testowe do modelu: %MODEL%...
echo Oczekuj na odpowiedz (moze to potrwac kilka sekund przy pierwszym ladowaniu).
echo.

curl.exe -X POST http://127.0.0.1:8000/v1/chat/completions ^
-H "Content-Type: application/json" ^
-H "Authorization: Bearer %API_KEY%" ^
-d "{\"model\": \"%MODEL%\", \"messages\": [{\"role\": \"user\", \"content\": \"Napisz krotko 'Wszystko dziala!'\"}]}"

echo.
echo.
pause
