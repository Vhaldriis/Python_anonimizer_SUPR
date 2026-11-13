import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(monkeypatch, store):
    """Приложение без PostgreSQL и без обращений к провайдерам ИИ."""
    sent = {}

    def fake_send_message(messages, provider, **kwargs):
        sent["messages"] = messages
        sent["provider"] = provider
        # Модель "отвечает" теми же псевдонимами, что получила
        return {"text": "Ответ для " + messages[-1]["content"], "model": "fake", "provider": provider,
                "usage": {"input_tokens": 1, "output_tokens": 1}}

    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "send_message", fake_send_message)
    monkeypatch.setattr(main, "get_full_map", store.get_full_map)
    with TestClient(main.app) as c:
        c.sent = sent
        yield c


def test_chat_never_sends_personal_data_and_restores_answer(client):
    resp = client.post(
        "/chat",
        headers={"X-User-ID": "1", "X-Session-ID": "chat_123"},
        json={"messages": [{"role": "user", "content": "Я Иван Иванов, ivan@company.ru"}], "provider": "nvidia"},
    )
    body = resp.json()
    assert resp.status_code == 200 and body["success"] is True
    outgoing = client.sent["messages"][0]["content"]
    assert outgoing == "Я [ИМЯ_1], [EMAIL_1]"
    assert body["text"] == "Ответ для Я Иван Иванов, ivan@company.ru"
    assert body["provider"] == "nvidia"


def test_map_returns_list_of_items(client):
    client.post("/chat", headers={"X-Session-ID": "m"}, json={"messages": [{"role": "user", "content": "a@b.ru"}]})
    body = client.get("/map/m", headers={"X-User-ID": "1"}).json()
    assert body == {"success": True, "map": [{"pseudonym": "[EMAIL_1]", "original": "a@b.ru", "field_type": "email"}]}


@pytest.mark.parametrize("method,path", [("post", "/chat"), ("get", "/map/s"), ("post", "/clear/s")])
def test_non_numeric_user_id_is_400(client, method, path):
    kwargs = {"headers": {"X-User-ID": "abc"}}
    if path == "/chat":
        kwargs["json"] = {"messages": [{"role": "user", "content": "hi"}]}
    resp = getattr(client, method)(path, **kwargs)
    assert resp.status_code == 400


def test_models_hides_providers_without_real_key(client, monkeypatch):
    monkeypatch.setenv("CLAUDE_API_KEY", "sk-ant-your-key-here")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-real")
    monkeypatch.delenv("DEFAULT_PROVIDER", raising=False)
    body = client.get("/models").json()
    assert [p["id"] for p in body["providers"]] == ["nvidia"]
    assert body["default_provider"] == "nvidia"


def test_unknown_provider_models_404(client):
    assert client.get("/models/unknown").status_code == 404


def test_ui_is_served(client):
    resp = client.get("/ui")
    assert resp.status_code == 200 and "<html" in resp.text.lower()
