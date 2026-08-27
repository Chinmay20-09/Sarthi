"""Tests for LocalHermesProvider (Ollama), verifying it uses the local model name."""

import httpx

from hermes.config.settings import HermesConfig
from hermes.models import Task
from hermes.providers.local_provider import LocalHermesProvider


class FakeOllamaResponse:
    """Minimal stand-in for httpx.Response with a successful chat payload."""

    def __init__(self, content: str = "Hello from Ollama"):
        self._content = content

    def raise_for_status(self) -> None:
        """No-op; the request succeeded."""

    def json(self) -> dict:
        return {"message": {"content": self._content}}


def _make_response_success() -> FakeOllamaResponse:
    return FakeOllamaResponse()


def _make_response_404() -> httpx.Response:
    request = httpx.Request("POST", "http://localhost:11434/api/chat")
    return httpx.Response(
        404, request=request, json={"error": "model 'x' not found, try pulling it first"}
    )


def test_uses_local_model_not_openrouter_model(monkeypatch):
    """The request to Ollama must use local_model, not the OpenRouter model name."""
    config = HermesConfig(model="openai/gpt-5", local_model="hermes3:8b")
    provider = LocalHermesProvider(config)

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _make_response_success()

    monkeypatch.setattr(provider._client, "post", fake_post)

    response = provider.generate(Task(prompt="Say hello"))

    assert response.success is True
    assert response.provider == "Ollama"
    assert response.model == "hermes3:8b"
    assert response.text == "Hello from Ollama"

    # The model sent to Ollama must be the local one, never the OpenRouter model.
    assert captured["json"]["model"] == "hermes3:8b"
    assert captured["json"]["model"] != config.model
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["json"]["messages"] == [{"role": "user", "content": "Say hello"}]


def test_falls_back_to_generic_model_when_local_model_empty(monkeypatch):
    """Backward compatibility: empty local_model falls back to config.model."""
    config = HermesConfig(model="openai/gpt-5", local_model="")
    provider = LocalHermesProvider(config)

    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        return _make_response_success()

    monkeypatch.setattr(provider._client, "post", fake_post)

    response = provider.generate(Task(prompt="Say hello"))

    assert response.success is True
    assert response.model == "openai/gpt-5"
    assert captured["json"]["model"] == "openai/gpt-5"


def test_404_reports_ollama_error_body(monkeypatch):
    """A 404 from Ollama should surface Ollama's error message for easy diagnosis."""
    config = HermesConfig(model="openai/gpt-5", local_model="hermes3:8b")
    provider = LocalHermesProvider(config)

    def fake_post(url, **kwargs):
        request = httpx.Request("POST", url)
        raise httpx.HTTPStatusError("Not Found", request=request, response=_make_response_404())

    monkeypatch.setattr(provider._client, "post", fake_post)

    response = provider.generate(Task(prompt="Say hello"))

    assert response.success is False
    assert response.provider == "Ollama"
    assert "HTTP 404" in response.error
    assert "model 'x' not found" in response.error
