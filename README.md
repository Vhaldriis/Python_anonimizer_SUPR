# Claude Anonymizer Proxy

Прослойка (обратный прокси) для защиты конфиденциальности пользователей при общении с ИИ-моделями (Anthropic Claude, OpenAI, NVIDIA NIM). Персональные данные заменяются на псевдонимы с уникальными числовыми подписями перед отправкой в ИИ, а в ответе восстанавливаются из локальной базы данных.

**Путь проекта:** `C:\Users\vlsta\projects\Python_anonimizer_SUPR`

## Возможности

- 🔐 **Обезличивание персональных данных** — имена, телефоны, email, ИНН, названия компаний заменяются на псевдонимы вида `[ИМЯ_1]`, `[TEL_1]`, `[EMAIL_1]`, `[ОРГ_1]`
- 🔄 **Обратная подстановка** — в ответе ИИ псевдонимы заменяются на реальные значения из локальной PostgreSQL
- 🤖 **Несколько провайдеров** — Claude, OpenAI, NVIDIA NIM (выбирается в веб-интерфейсе)
- 📂 **Прикрепление файлов** — изображения (только для Claude) и текстовые файлы к сообщениям
- 🏢 **Интеграция с Bitrix24** — синхронизация компаний и контактов из портала для точного псевдонимизирования
- 📊 **Веб-интерфейс** — современный чат с выбором провайдера и модели, карта псевдонимов
- 📝 **Аудит** — карта псевдонимов сессии доступна через `GET /map/{session_id}`; расход токенов возвращается в ответе `/chat`

## Структура проекта

```
Python_anonimizer_SUPR/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI сервер и все эндпоинты
│   ├── database.py          # PostgreSQL: псевдонимы, сущности Bitrix24
│   ├── anonymizer.py        # Замена данных на псевдонимы (БД + regex)
│   ├── ai_client.py         # Клиенты Claude / OpenAI / NVIDIA
│   ├── bitrix24_sync.py     # Синхронизация из Bitrix24
│   ├── claude_client.py     # Устаревший клиент только для Claude (не используется)
│   └── models.py            # Pydantic-схемы
├── static/
│   └── index.html           # Веб-интерфейс чата
├── tests/                   # Тесты (pytest), БД и сеть не требуются
├── .env                     # Локальная конфигурация (создаётся из .env.example, не коммитится)
├── .env.example             # Шаблон .env
├── init_db.sql              # Схема PostgreSQL (приложение также создаёт таблицы при старте)
├── deploy.ps1               # Скрипт развёртывания для Windows (PowerShell)
├── setup.bat                # Установка зависимостей для Windows
├── РАЗВЁРТЫВАНИЕ.md         # Пошаговая инструкция по развёртыванию
├── requirements.txt         # Python зависимости
└── README.md
```

## Требования

- Python 3.10+
- PostgreSQL 14+
- Ключ API от Anthropic (Claude), OpenAI или NVIDIA NIM (хотя бы один)

## Быстрый старт

### 1. Установите зависимости

```powershell
cd C:\Users\vlsta\projects\Python_anonimizer_SUPR
python -m pip install -r requirements.txt
```

### 2. Настройте PostgreSQL

Создайте базу данных и пользователя (пример для `psql`):

```powershell
psql -U postgres -d postgres -c "CREATE USER app_user WITH PASSWORD 'ВАШ_ПАРОЛЬ';"
psql -U postgres -d postgres -c "CREATE DATABASE claude_anonimizer OWNER app_user ENCODING 'UTF8' TEMPLATE template0;"
```

База должна принадлежать `app_user`: в PostgreSQL 15+ одного `GRANT ALL PRIVILEGES ON DATABASE` недостаточно для создания таблиц в схеме `public`.

Примените схему:

```powershell
psql -U app_user -d claude_anonimizer -f init_db.sql
```

Этот шаг необязателен: при старте приложение само создаёт недостающие таблицы (включая `custom_entities` для Bitrix24, которой нет в `init_db.sql`).

Если `psql` не найден, укажите полный путь, например:
`C:\Program Files\PostgreSQL\16\bin\psql.exe`

### 3. Настройте `.env`

Скопируйте шаблон и укажите свои значения:

```powershell
Copy-Item .env.example .env
```

```
CLAUDE_API_KEY=sk-ant-ВАШ_КЛЮЧ
OPENAI_API_KEY=sk-ВАШ_КЛЮЧ
NVIDIA_API_KEY=nvapi-ВАШ_КЛЮЧ
DATABASE_URL=postgresql://app_user:ВАШ_ПАРОЛЬ@localhost:5432/claude_anonimizer
BITRIX24_WEBHOOK_URL=https://ВАШ_ПОРТАЛ/rest/ID_ПОЛЬЗОВАТЕЛЯ/КОД_ВЕБХУКА/
DEFAULT_PROVIDER=nvidia
```

Минимум один из ключей (`CLAUDE_API_KEY`, `OPENAI_API_KEY`, `NVIDIA_API_KEY`) должен быть реальным, а не placeholder'ом.

| Переменная | Обязательна | По умолчанию | Назначение |
|------------|-------------|--------------|------------|
| `CLAUDE_API_KEY` / `OPENAI_API_KEY` / `NVIDIA_API_KEY` | хотя бы одна | — | Ключи провайдеров |
| `CLAUDE_MODEL` | нет | `claude-3-haiku-20240307` | Модель Claude по умолчанию |
| `OPENAI_MODEL` | нет | `gpt-4o-mini` | Модель OpenAI по умолчанию |
| `NVIDIA_MODEL` | нет | `meta/llama-3.1-8b-instruct` | Модель NVIDIA по умолчанию |
| `NVIDIA_BASE_URL` | нет | `https://integrate.api.nvidia.com/v1` | Базовый URL NVIDIA NIM |
| `DATABASE_URL` | рекомендуется | `postgresql://postgres:2912@localhost:5432/claude_anonimizer` (зашито в `app/database.py`) | `postgresql://user:password@host:port/dbname` |
| `DEFAULT_PROVIDER` | нет | первый доступный | Провайдер, выбранный в интерфейсе |
| `BITRIX24_WEBHOOK_URL` | нет | пусто | Вебхук для синхронизации CRM |
| `LOG_LEVEL` | нет | `INFO` | Уровень логирования |

### 4. Запустите сервер

```powershell
cd C:\Users\vlsta\projects\Python_anonimizer_SUPR
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Запускать нужно из корня проекта: путь к `static/` задан относительно текущей директории.

> ⚠️ В API нет аутентификации: `X-User-ID` принимается на веру, а `/map` и `/bitrix24/entities` отдают реальные данные. Не открывайте порт наружу (`--host 0.0.0.0`) без обратного прокси с авторизацией.

### 5. Откройте веб-интерфейс

```
http://localhost:8000/ui
```

Укажите `User ID`, `Session ID`, выберите провайдера и модель — и можно писать сообщения.

## API эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/chat` | Отправить сообщение в ИИ с обезличиванием (поддержка файлов) |
| GET | `/models` | Список доступных провайдеров |
| GET | `/models/{provider}` | Список моделей конкретного провайдера |
| POST | `/bitrix24/sync` | Синхронизировать компании и контакты из Bitrix24 |
| GET | `/bitrix24/entities` | Список синхронизированных сущностей с псевдонимами |
| GET | `/map/{session_id}` | Карта псевдонимов сессии |
| POST | `/clear/{session_id}` | Очистить карту псевдонимов |
| GET | `/ui` | Веб-интерфейс чата |

Пример запроса к `/chat`:

```json
POST http://localhost:8000/chat
Headers:
  X-User-ID: 1
  X-Session-ID: chat_123
  Content-Type: application/json

Body:
{
  "messages": [{"role": "user", "content": "Здравствуйте, я Иван Иванов из ООО 'Техно', телефон +7 999 123 45 67"}],
  "session_id": "chat_123",
  "user_id": 1,
  "provider": "nvidia",
  "model": "meta/llama-3.1-8b-instruct"
}
```

## Интеграция с Bitrix24

1. Укажите вебхук портала в `.env` (`BITRIX24_WEBHOOK_URL`)
2. В настройках вебхука в Bitrix24 дайте права на чтение CRM
3. Запустите синхронизацию:
   ```powershell
   Invoke-WebRequest -Method Post -Uri "http://localhost:8000/bitrix24/sync" -Headers @{"X-User-ID"="1"} -UseBasicParsing
   ```
4. Названия компаний и имена контактов из Bitrix24 (в виде «Фамилия Имя») будут автоматически заменяться на псевдонимы в чате. Поиск идёт по точному вхождению строки с учётом регистра.

## Анонимизация данных

Работает в два этапа:

1. **Из базы Bitrix24** — известные компании и контакты заменяются на псевдонимы (например, `ООО "Илюха монеси"` → `[ОРГ_1]`)
2. **По регулярным выражениям** — остальные телефоны, email, ИНН, имена заменяются на псевдонимы с уникальными номерами

В ответе от ИИ все псевдонимы автоматически восстанавливаются в реальные значения из локальной базы.

## Прикрепление файлов

В веб-чате нажмите кнопку 📎 и прикрепите:
- Изображения (JPG, PNG, WebP и др.) — отправляются как мультимодальный контент только провайдеру Claude; для OpenAI и NVIDIA изображения не передаются. **Изображения не обезличиваются** — не прикрепляйте сканы с персональными данными
- Текстовые файлы (TXT, CSV и другие `text/*`) — содержимое обезличивается и добавляется к сообщению
- PDF, DOC, DOCX — извлечение текста не реализовано; модели уходит только пометка, что вложение не поддерживается

Лимит: 10 МБ на файл (проверяется только в веб-интерфейсе, не на сервере).

## Тесты

```powershell
python -m pip install pytest
python -m pytest
```

Тесты не требуют PostgreSQL и не обращаются к провайдерам ИИ.

## Безопасность

- Карта псевдонимов хранится только локально в PostgreSQL и никогда не уходит к провайдеру ИИ
- Ключи API храните в `.env` (не коммитьте в репозиторий; файл указан в `.gitignore`)
- Используйте HTTPS и обратный прокси с авторизацией в продакшене — собственной аутентификации в приложении нет
- Обезличивание основано на регулярных выражениях и не гарантирует удаление всех персональных данных (адреса, имена в косвенных падежах, отчества, данные на изображениях не распознаются)

---

Развёртывание и поддержка: `C:\Users\vlsta\projects\Python_anonimizer_SUPR`
