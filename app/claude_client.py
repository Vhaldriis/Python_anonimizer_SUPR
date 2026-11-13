import os
from typing import List, Dict, Any, Optional
from anthropic import Anthropic

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-haiku-20240307")

if not CLAUDE_API_KEY:
    raise RuntimeError("CLAUDE_API_KEY не задан. Укажите в .env")

client = Anthropic(api_key=CLAUDE_API_KEY)


def send_message(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    system: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Отправляет сообщения в Claude API.
    messages: список {"role": "user"/"assistant"/"system", "content": "..."}
    """
    model = model or CLAUDE_MODEL

    kwargs: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }

    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)

    # Извлекаем текст из блоков контента
    text_parts = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)

    return {
        "text": "\n".join(text_parts),
        "model": response.model,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        "raw": response,
    }
