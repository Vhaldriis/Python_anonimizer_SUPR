import os
import base64
from typing import List, Dict, Any, Optional
import httpx

from app.anonymizer import anonymize_text

# ---------- Клиенты ----------
_anthropic_client = None
_openai_client = None


def get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic
        api_key = os.getenv("CLAUDE_API_KEY")
        if not api_key:
            raise RuntimeError("CLAUDE_API_KEY не задан в .env")
        _anthropic_client = Anthropic(api_key=api_key)
    return _anthropic_client


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY не задан в .env")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# ---------- Отправка сообщения ----------
def send_message(
    messages: List[Dict[str, str]],
    provider: str = "claude",
    model: Optional[str] = None,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    system: Optional[str] = None,
    files: List[Dict[str, Any]] = None,
    user_id: int = 0,
    session_id: str = "",
) -> Dict[str, Any]:
    """
    Отправляет сообщения в выбранную ИИ-модель.
    provider: claude | openai | nvidia
    files: список вложений [{name, type, size, base64}, ...]
    """
    provider = provider.lower()
    files = files or []

    # Обработка вложений: добавляем их содержимое в первое пользовательское сообщение
    if files:
        file_descriptions = []
        image_blocks = []

        for f in files:
            fname = f.get("name", "файл")
            ftype = f.get("type", "")
            b64 = f.get("base64", "")

            # Изображения — отправляем как мультимодальный контент
            if ftype.startswith("image/"):
                image_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": ftype,
                        "data": b64,
                    },
                })
            # Текстовые файлы — извлекаем текст, обезличиваем и добавляем к сообщению.
            # PDF/DOC/DOCX — бинарные форматы: декодировать их как UTF-8 нельзя
            # (получается мусор, в котором regex не находит персональные данные),
            # поэтому они попадают в ветку "не поддерживается".
            elif ftype.startswith("text/"):
                try:
                    file_text = base64.b64decode(b64).decode("utf-8", errors="ignore")
                    # Обезличиваем содержимое текстового файла
                    safe_text = anonymize_text(file_text, user_id, session_id)
                    file_descriptions.append(
                        f"\n--- Вложение: {fname} ---\n{safe_text}\n--- Конец вложения ---\n"
                    )
                except Exception as e:
                    file_descriptions.append(
                        f"\n--- Вложение: {fname} (не удалось прочитать: {e}) ---\n"
                    )
            else:
                file_descriptions.append(
                    f"\n--- Вложение: {fname} (тип: {ftype}, не поддерживается для анализа) ---\n"
                )

        # Добавляем описания файлов к первому пользовательскому сообщению
        if file_descriptions:
            for m in messages:
                if m.get("role") == "user":
                    m["content"] = m.get("content", "") + "".join(file_descriptions)
                    break

        # Для Claude: изображения добавляем как отдельные блоки в контент первого пользовательского сообщения
        if image_blocks and provider == "claude":
            for m in messages:
                if m.get("role") == "user":
                    content_blocks = [{"type": "text", "text": m.get("content", "")}]
                    content_blocks.extend(image_blocks)
                    m["content"] = content_blocks
                    break

    provider = provider.lower()

    if provider == "claude":
        return _send_claude(messages, model, max_tokens, temperature, system)

    if provider == "openai":
        return _send_openai(messages, model, max_tokens, temperature, system)

    if provider == "nvidia":
        return _send_nvidia(messages, model, max_tokens, temperature, system)

    raise ValueError(f"Неизвестный провайдер: {provider}")


# ---------- Anthropic Claude ----------
def _send_claude(
    messages: List[Dict[str, str]],
    model: Optional[str],
    max_tokens: int,
    temperature: float,
    system: Optional[str],
) -> Dict[str, Any]:
    client = get_anthropic_client()
    model = model or os.getenv("CLAUDE_MODEL", "claude-3-haiku-20240307")

    # Разделяем system и остальные сообщения для Claude
    system_msg = system or ""
    chat_messages = []
    for m in messages:
        if m["role"] == "system":
            system_msg = m["content"]
        else:
            chat_messages.append(m)

    kwargs: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": chat_messages,
    }
    if system_msg:
        kwargs["system"] = system_msg

    response = client.messages.create(**kwargs)

    text_parts = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)

    return {
        "text": "\n".join(text_parts),
        "model": response.model,
        "provider": "claude",
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        "raw": response,
    }


# ---------- OpenAI ----------
def _send_openai(
    messages: List[Dict[str, str]],
    model: Optional[str],
    max_tokens: int,
    temperature: float,
    system: Optional[str],
) -> Dict[str, Any]:
    client = get_openai_client()
    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Формируем массив сообщений для OpenAI (system включается в messages)
    formatted_messages = []
    if system:
        formatted_messages.append({"role": "system", "content": system})
    formatted_messages.extend(messages)

    response = client.chat.completions.create(
        model=model,
        messages=formatted_messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    text = response.choices[0].message.content or ""

    return {
        "text": text,
        "model": response.model,
        "provider": "openai",
        "usage": {
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
        },
        "raw": response,
    }


# ---------- NVIDIA NIM ----------
def _send_nvidia(
    messages: List[Dict[str, str]],
    model: Optional[str],
    max_tokens: int,
    temperature: float,
    system: Optional[str],
) -> Dict[str, Any]:
    api_key = os.getenv("NVIDIA_API_KEY")
    base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    model = model or os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")

    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY не задан в .env")

    # NVIDIA NIM — OpenAI-совместимый API
    formatted_messages = []
    if system:
        formatted_messages.append({"role": "system", "content": system})
    formatted_messages.extend(messages)

    payload = {
        "model": model,
        "messages": formatted_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
        if resp.status_code >= 400:
            raise RuntimeError(f"NVIDIA API ошибка {resp.status_code}: {resp.text}")
        data = resp.json()

    text = ""
    if data.get("choices"):
        text = data["choices"][0].get("message", {}).get("content", "")

    usage = data.get("usage", {})

    return {
        "text": text,
        "model": model,
        "provider": "nvidia",
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
        "raw": data,
    }
