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


def _timeout_error(url: str) -> httpx.ReadTimeout:
    """A ReadTimeout shaped like httpx raises on an over-budget generation."""
    return httpx.ReadTimeout("timed out", request=httpx.Request("POST", url))


def test_retries_once_on_timeout_then_succeeds(monkeypatch):
    """A timeout (cold model load) is retried once; the warm retry succeeds."""
    config = HermesConfig(model="openai/gpt-5", local_model="hermes3:8b")
    provider = LocalHermesProvider(config)

    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _timeout_error(url)
        return _make_response_success()

    monkeypatch.setattr(provider._client, "post", fake_post)

    response = provider.generate(Task(prompt="Say hello"))

    assert calls["n"] == 2
    assert response.success is True
    assert response.provider == "Ollama"
    assert response.text == "Hello from Ollama"


def test_does_not_retry_more_than_once_on_timeout(monkeypatch):
    """Two consecutive timeouts still fail with the standard timeout error."""
    config = HermesConfig(model="openai/gpt-5", local_model="hermes3:8b")
    provider = LocalHermesProvider(config)

    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        raise _timeout_error(url)

    monkeypatch.setattr(provider._client, "post", fake_post)

    response = provider.generate(Task(prompt="Say hello"))

    assert calls["n"] == 2
    assert response.success is False
    assert response.error == "Connection timeout"


def test_non_timeout_errors_are_not_retried(monkeypatch):
    """HTTP errors (e.g. model missing) fail immediately — no pointless retry."""
    config = HermesConfig(model="openai/gpt-5", local_model="hermes3:8b")
    provider = LocalHermesProvider(config)

    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        request = httpx.Request("POST", url)
        raise httpx.HTTPStatusError("Not Found", request=request, response=_make_response_404())

    monkeypatch.setattr(provider._client, "post", fake_post)

    response = provider.generate(Task(prompt="Say hello"))

    assert calls["n"] == 1
    assert response.success is False
    assert "HTTP 404" in response.error
