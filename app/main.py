import os
import logging
from typing import Optional
from dotenv import load_dotenv
load_dotenv()

import httpx

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db, get_full_map, clear_map, get_all_entities
from app.anonymizer import anonymize_text, deanonymize_text
from app.ai_client import send_message
from app.bitrix24_sync import sync_all_bitrix24_entities
from app.models import ChatRequest, ChatResponse, MapResponse

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("claude_anonimizer")

app = FastAPI(title="Claude Anonymizer Proxy", version="1.0.0")

# Подключаем статику (веб-интерфейс), если папка существует
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception:
    pass


@app.on_event("startup")
def startup():
    init_db()
    logger.info("База данных инициализирована")


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head><title>Claude Anonymizer Proxy</title></head>
        <body style="font-family:system-ui;background:#0f172a;color:#e2e8f0;padding:40px;">
            <h1>🔐 Claude Anonymizer Proxy</h1>
            <p>API работает. Доступные эндпоинты:</p>
            <ul>
                <li><code>POST /chat</code> — отправка сообщения в ИИ с обезличиванием (provider: claude, openai, nvidia)</li>
                <li><code>GET /map/{session_id}</code> — карта псевдонимов сессии</li>
                <li><code>POST /clear/{session_id}</code> — очистка карты сессии</li>
                <li><code>GET /ui</code> — веб-чат</li>
            </ul>
            <p style="margin-top:24px;color:#94a3b8;font-size:14px;">
                Пример заголовков: <code>X-User-ID: 1</code>, <code>X-Session-ID: chat_123</code>
            </p>
        </body>
    </html>
    """


@app.get("/ui", response_class=HTMLResponse)
async def ui():
    """Простой веб-чат для тестирования."""
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(
            content="<p>Веб-интерфейс не найден. Создайте файл static/index.html</p>",
            status_code=404,
        )


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    x_user_id: Optional[str] = Header(None),
    x_session_id: Optional[str] = Header(None),
):
    """
    Основной эндпоинт:
    1. Анонимизирует входящие сообщения (заменяет персональные данные на псевдонимы с уникальными номерами).
    2. Отправляет анонимный текст в выбранную ИИ-модель (Claude / OpenAI / NVIDIA).
    3. Деанимизирует ответ (подставляет реальные значения из локальной PostgreSQL).
    """
    user_id = int(x_user_id) if x_user_id else request.user_id
    session_id = x_session_id or request.session_id
    provider = request.provider or "claude"

    try:
        # 1. Анонимизация входящих сообщений
        safe_messages = []
        for msg in request.messages:
            safe_content = anonymize_text(msg.content, user_id, session_id)
            safe_messages.append({"role": msg.role, "content": safe_content})

        # 2. Запрос к выбранному провайдеру
        result = send_message(
            messages=safe_messages,
            provider=provider,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            files=[f.model_dump() for f in request.files],
            user_id=user_id,
            session_id=session_id,
        )

        # 3. Деанимизация ответа (подстановка реальных значений из БД)
        clean_text = deanonymize_text(result["text"], user_id, session_id)

        return ChatResponse(
            success=True,
            text=clean_text,
            model=result.get("model"),
            provider=result.get("provider"),
            usage=result.get("usage"),
        )

    except Exception as e:
        logger.exception("Ошибка в /chat")
        return ChatResponse(success=False, error=str(e))


def _provider_available(env_key: str) -> bool:
    """Проверяет, задан ли API-ключ провайдера в окружении."""
    val = os.getenv(env_key, "")
    return bool(val) and not val.startswith("sk-ant-your-key") and not val.startswith("sk-your-key") and not val.startswith("nvapi-your-key")


@app.get("/models")
async def list_models():
    """Возвращает список доступных провайдеров (у которых есть API-ключ) и их модели."""
    all_providers = [
        {
            "id": "claude",
            "name": "Anthropic Claude",
            "api_url": "https://api.anthropic.com/v1/messages",
            "models": [
                {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku (быстрый, дешёвый)"},
                {"id": "claude-3-sonnet-20240229", "name": "Claude 3 Sonnet (сбалансированный)"},
                {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus (самый мощный)"},
            ],
            "default_model": os.getenv("CLAUDE_MODEL", "claude-3-haiku-20240307"),
            "env_key": "CLAUDE_API_KEY",
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "api_url": "https://api.openai.com/v1/chat/completions",
            "models": [
                {"id": "gpt-4o-mini", "name": "GPT-4o Mini (быстрый, дешёвый)"},
                {"id": "gpt-4o", "name": "GPT-4o (мощный)"},
                {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo (устаревший)"},
            ],
            "default_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "env_key": "OPENAI_API_KEY",
        },
        {
            "id": "nvidia",
            "name": "NVIDIA NIM",
            "api_url": "https://integrate.api.nvidia.com/v1/chat/completions",
            "models": [
                {"id": "meta/llama-3.1-8b-instruct", "name": "Llama 3.1 8B Instruct"},
                {"id": "meta/llama-3.1-70b-instruct", "name": "Llama 3.1 70B Instruct"},
                {"id": "mistralai/mistral-7b-instruct-v0.3", "name": "Mistral 7B Instruct v0.3"},
                {"id": "google/gemma-2-9b-it", "name": "Gemma 2 9B IT"},
            ],
            "default_model": os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct"),
            "env_key": "NVIDIA_API_KEY",
        },
    ]

    available = [p for p in all_providers if _provider_available(p["env_key"])]
    return {
        "providers": available,
        "default_provider": os.getenv("DEFAULT_PROVIDER", available[0]["id"] if available else "claude"),
    }


# ---------- Статичные списки моделей (fallback, если API провайдера недоступно) ----------
STATIC_MODELS = {
    "claude": [
        {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku (быстрый, дешёвый)"},
        {"id": "claude-3-sonnet-20240229", "name": "Claude 3 Sonnet (сбалансированный)"},
        {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus (самый мощный)"},
    ],
    "openai": [
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini (быстрый, дешёвый)"},
        {"id": "gpt-4o", "name": "GPT-4o (мощный)"},
        {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo (устаревший)"},
    ],
    "nvidia": [
        {"id": "meta/llama-3.1-8b-instruct", "name": "Llama 3.1 8B Instruct"},
        {"id": "meta/llama-3.1-70b-instruct", "name": "Llama 3.1 70B Instruct"},
        {"id": "mistralai/mistral-7b-instruct-v0.3", "name": "Mistral 7B Instruct v0.3"},
        {"id": "google/gemma-2-9b-it", "name": "Gemma 2 9B IT"},
    ],
}

PROVIDER_MODELS_URL = {
    "claude": "https://api.anthropic.com/v1/models",
    "openai": "https://api.openai.com/v1/models",
    "nvidia": "https://integrate.api.nvidia.com/v1/models",
}


async def _fetch_models_from_provider(provider: str, api_key: str) -> list[dict] | None:
    """Пытается получить список моделей напрямую от API провайдера."""
    url = PROVIDER_MODELS_URL.get(provider)
    if not url:
        return None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    if provider == "claude":
        headers["anthropic-version"] = "2023-06-01"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code >= 400:
                return None
            data = resp.json()

        if provider == "claude":
            # Anthropic возвращает {"data": [{"id": "..."}, ...]}
            return [{"id": m["id"], "name": m["id"]} for m in data.get("data", [])]

        if provider == "openai":
            # OpenAI возвращает {"data": [{"id": "gpt-4o", ...}, ...]}
            return [{"id": m["id"], "name": m["id"]} for m in data.get("data", [])]

        if provider == "nvidia":
            # NVIDIA может возвращать разные форматы — пробуем data / models
            items = data.get("data") or data.get("models") or []
            return [{"id": m.get("id") or m.get("name"), "name": m.get("id") or m.get("name")} for m in items if m.get("id") or m.get("name")]

    except Exception:
        return None

    return None


@app.get("/models/{provider}")
async def get_provider_models(provider: str, x_user_id: Optional[str] = Header(None)):
    """Возвращает список моделей для конкретного провайдера.
    Сначала пробует загрузить из API провайдера, затем fallback на статичный список.
    """
    env_key_map = {"claude": "CLAUDE_API_KEY", "openai": "OPENAI_API_KEY", "nvidia": "NVIDIA_API_KEY"}
    env_key = env_key_map.get(provider)
    if not env_key:
        raise HTTPException(status_code=404, detail="Unknown provider")

    api_key = os.getenv(env_key, "")
    if not api_key or api_key.startswith("sk-ant-your-key") or api_key.startswith("sk-your-key") or api_key.startswith("nvapi-your-key"):
        raise HTTPException(status_code=401, detail="API key not configured for this provider")

    # 1. Пробуем живой API
    live_models = await _fetch_models_from_provider(provider, api_key)
    if live_models:
        default_model = os.getenv(f"{provider.upper()}_MODEL", live_models[0]["id"])
        return {
            "provider": provider,
            "models": live_models,
            "default_model": default_model,
            "source": "api",
        }

    # 2. Fallback на статичный список
    static_models = STATIC_MODELS.get(provider, [])
    default_model = os.getenv(f"{provider.upper()}_MODEL", static_models[0]["id"] if static_models else "")
    return {
        "provider": provider,
        "models": static_models,
        "default_model": default_model,
        "source": "static",
    }


@app.get("/map/{session_id}", response_model=MapResponse)
async def get_map(session_id: str, x_user_id: Optional[str] = Header(None)):
    """Возвращает карту псевдонимов для сессии (отладка/аудит)."""
    user_id = int(x_user_id) if x_user_id else 1
    mapping = get_full_map(user_id, session_id)
    return MapResponse(success=True, map=mapping)


@app.post("/clear/{session_id}", response_model=MapResponse)
async def clear_session_map(session_id: str, x_user_id: Optional[str] = Header(None)):
    """Очищает карту псевдонимов и счётчики для сессии."""
    user_id = int(x_user_id) if x_user_id else 1
    clear_map(user_id, session_id)
    return MapResponse(success=True, map=[])


@app.post("/bitrix24/sync")
async def bitrix24_sync(x_user_id: Optional[str] = Header(None)):
    """Синхронизирует компании и контакты из Bitrix24 как известные сущности для анонимизации."""
    result = await sync_all_bitrix24_entities()
    return {"success": True, "synced": result}


@app.get("/bitrix24/entities")
async def bitrix24_entities():
    """Возвращает все синхронизированные сущности Bitrix24 с их псевдонимами."""
    entities = get_all_entities()
    return {"success": True, "count": len(entities), "entities": entities}
