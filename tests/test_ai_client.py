import base64

import pytest

from app import ai_client


@pytest.fixture
def captured(monkeypatch):
    """Перехватывает сообщения, уходящие провайдеру, без сетевых вызовов."""
    calls = {}

    def fake(provider):
        def _send(messages, model, max_tokens, temperature, system):
            calls["provider"] = provider
            calls["messages"] = messages
            calls["system"] = system
            return {"text": "ok", "model": model, "provider": provider, "usage": {}}
        return _send

    monkeypatch.setattr(ai_client, "_send_claude", fake("claude"))
    monkeypatch.setattr(ai_client, "_send_openai", fake("openai"))
    monkeypatch.setattr(ai_client, "_send_nvidia", fake("nvidia"))
    monkeypatch.setattr(ai_client, "anonymize_text", lambda text, u, s: text.replace("Иван Иванов", "[ИМЯ_1]"))
    return calls


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_unknown_provider(captured):
    with pytest.raises(ValueError):
        ai_client.send_message([{"role": "user", "content": "hi"}], provider="nope")


def test_text_attachment_is_anonymized(captured):
    files = [{"name": "a.txt", "type": "text/plain", "size": 1, "base64": b64("Иван Иванов".encode())}]
    ai_client.send_message([{"role": "user", "content": "см. файл"}], provider="openai", files=files)
    content = captured["messages"][0]["content"]
    assert "[ИМЯ_1]" in content and "Иван Иванов" not in content


@pytest.mark.parametrize("mime", [
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
])
def test_binary_documents_are_not_sent_as_garbage(captured, mime):
    payload = "%PDF-1.7 Иван Иванов".encode()
    files = [{"name": "doc.bin", "type": mime, "size": 1, "base64": b64(payload)}]
    ai_client.send_message([{"role": "user", "content": "см. файл"}], provider="openai", files=files)
    content = captured["messages"][0]["content"]
    assert "не поддерживается" in content
    assert "Иван Иванов" not in content and "%PDF" not in content


def test_image_goes_to_claude_as_block(captured):
    files = [{"name": "p.png", "type": "image/png", "size": 1, "base64": "AAAA"}]
    ai_client.send_message([{"role": "user", "content": "что тут?"}], provider="claude", files=files)
    content = captured["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "что тут?"}
    assert content[1]["source"]["media_type"] == "image/png"


class _FakeCompletions:
    def __init__(self, sink):
        self.sink = sink

    def create(self, **kwargs):
        self.sink.update(kwargs)

        class Msg:
            content = "ответ"

        class Choice:
            message = Msg()

        class Resp:
            choices = [Choice()]
            model = kwargs["model"]
            usage = None

        return Resp()


def test_openai_keeps_system_messages(monkeypatch):
    sink = {}

    class FakeClient:
        class chat:
            completions = _FakeCompletions(sink)

    monkeypatch.setattr(ai_client, "get_openai_client", lambda: FakeClient)
    messages = [{"role": "system", "content": "Отвечай кратко"}, {"role": "user", "content": "привет"}]
    result = ai_client.send_message(messages, provider="openai", model="m")
    assert sink["messages"] == messages
    assert result["text"] == "ответ"
