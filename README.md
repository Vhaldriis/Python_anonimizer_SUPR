# Claude Anonymizer Proxy

Прослойка (обратный прокси) для защиты конфиденциальности пользователей при общении с ИИ-моделями (Anthropic Claude, OpenAI, NVIDIA NIM). Персональные данные заменяются на псевдонимы с уникальными числовыми подписями перед отправкой в ИИ, а в ответе восстанавливаются из локальной базы данных.

**Путь проекта:** `C:\Users\vlsta\projects\Python_anonimizer_SUPR`

## Возможности

- 🔐 **Обезличивание персональных данных** — имена, телефоны, email, ИНН, названия компаний заменяются на псевдонимы вида `[ИМЯ_1]`, `[TEL_1]`, `[EMAIL_1]`, `[ОРГ_1]`
- 🔄 **Обратная подстановка** — в ответе ИИ псевдонимы заменяются на реальные значения из локальной PostgreSQL
- 🤖 **Несколько провайдеров** — Claude, OpenAI, NVIDIA NIM (выбирается в веб-интерфейсе)
- 📂 **Прикрепление файлов** — изображения и текстовые документы к сообщениям
- 🏢 **Интеграция с Bitrix24** — синхронизация компаний и контактов из портала для точного псевдонимизирования
- 📊 **Веб-интерфейс** — современный чат с выбором провайдера и модели, карта псевдонимов
- 📝 **Аудит** — логирование запросов и токенов

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
│   └── models.py            # Pydantic-схемы
├── static/
│   └── index.html           # Веб-интерфейс чата
├── .env                     # Конфигурация (ключи, URL БД, вебхук Bitrix24)
├── .env.example             # Шаблон .env
├── init_db.sql              # Схема PostgreSQL
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
psql -U postgres -d postgres -c "CREATE DATABASE claude_anonimizer;"
psql -U postgres -d postgres -c "CREATE USER app_user WITH PASSWORD '2912';"
psql -U postgres -d postgres -c "GRANT ALL PRIVILEGES ON DATABASE claude_anonimizer TO app_user;"
```

Примените схему:

```powershell
psql -U app_user -d claude_anonimizer -f init_db.sql
```

Если `psql` не найден, укажите полный путь, например:
`C:\Program Files\PostgreSQL\16\bin\psql.exe`

### 3. Настройте `.env`

Откройте `C:\Users\vlsta\projects\Python_anonimizer_SUPR\.env` и укажите:

```
CLAUDE_API_KEY=sk-ant-ВАШ_КЛЮЧ
OPENAI_API_KEY=sk-ВАШ_КЛЮЧ
NVIDIA_API_KEY=nvapi-ВАШ_КЛЮЧ
DATABASE_URL=postgresql://postgres:2912@localhost:5432/claude_anonimizer
BITRIX24_WEBHOOK_URL=https://bx.supr.ru/rest/16/rn1to8zs42aft2ou/
DEFAULT_PROVIDER=nvidia
```

Минимум один из ключей (`CLAUDE_API_KEY`, `OPENAI_API_KEY`, `NVIDIA_API_KEY`) должен быть реальным, а не placeholder'ом.

### 4. Запустите сервер

```powershell
cd C:\Users\vlsta\projects\Python_anonimizer_SUPR
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

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
4. Названия компаний и имена сотрудников из Bitrix24 будут автоматически заменяться на псевдонимы в чате.

## Анонимизация данных

Работает в два этапа:

1. **Из базы Bitrix24** — известные компании и контакты заменяются на псевдонимы (например, `ООО "Илюха монеси"` → `[ОРГ_1]`)
2. **По регулярным выражениям** — остальные телефоны, email, ИНН, имена заменяются на псевдонимы с уникальными номерами

В ответе от ИИ все псевдонимы автоматически восстанавливаются в реальные значения из локальной базы.

## Прикрепление файлов

В веб-чате нажмите кнопку 📎 и прикрепите:
- Изображения (JPG, PNG, WebP и др.) — отправляются ИИ как мультимодальный контент
- Текстовые файлы (TXT, PDF, DOC, DOCX) — содержимое извлекается, обезличивается и добавляется к сообщению

Лимит: 10 МБ на файл.

## Безопасность

- Карта псевдонимов хранится только локально в PostgreSQL и никогда не уходит к провайдеру ИИ
- Ключи API храните в `.env` (не коммитьте в репозиторий)
- Используйте HTTPS в продакшене
- Папки с логами и кэшем закрыты от прямого доступа

---

Развёртывание и поддержка: `C:\Users\vlsta\projects\Python_anonimizer_SUPR`
