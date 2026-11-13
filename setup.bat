@echo off
chcp 65001 >nul
echo ========================================
echo  Claude Anonymizer — развёртывание
echo ========================================

cd /d "%~dp0"

echo [1/5] Установка Python зависимостей...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ОШИБКА: не удалось установить зависимости
    pause
    exit /b 1
)

echo [2/5] Проверка переменной CLAUDE_API_KEY...
findstr /c:"CLAUDE_API_KEY=sk-ant-" .env >nul
if %errorlevel% neq 0 (
    echo ВНИМАНИЕ: В файле .env не указан реальный CLAUDE_API_KEY!
    echo Откройте .env и замените sk-ant-your-key-here на свой ключ Anthropic.
)

echo [3/5] Готово. Теперь настройте PostgreSQL (см. инструкцию ниже)
echo [4/5] После настройки БД запустите сервер:
echo         uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
echo [5/5] Откройте http://localhost:8000/ui

pause
