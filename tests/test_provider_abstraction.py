"""Focused tests for the Hermes provider abstraction.

Covers: the provider interface, config-driven selection (registry),
request normalization (Task -> ModelRequest), response normalization,
capability declaration, failure handling, structured-output flags,
tool-call handling through the single Hermes loop, Browser Awareness
independence, and the /hermes/status endpoint.

No live model or API key is required — providers are exercised with fake
HTTP responses, and adapter clients are monkeypatched so nothing reaches
the network.
"""

import httpx2
import pytest
from hermes.config.settings import HermesConfig
from hermes.models import ModelRequest, Task
from hermes.providers.base import AIProvider, ModelCapabilities, ProviderResponse
from hermes.providers.exceptions import ProviderUnavailable
from hermes.providers.local_provider import LocalHermesProvider
from hermes.providers.manager import ProviderManager
from hermes.providers.openai_compatible import OpenAICompatibleProvider
from hermes.providers.openrouter_provider import OpenRouterProvider
from hermes.providers.registry import (
    build_provider_manager,
    create_local_provider,
    is_local_only,
    provider_status,
    resolve_provider_name,
)

# ----------------------------------------------------------------------
# Fake HTTP responses / capture providers
# ----------------------------------------------------------------------


class FakeOllamaResponse:
    """Stand-in for httpx2.Response with Ollama's chat payload."""

    def __init__(self, content: str = "Hello from Ollama"):
        self._content = content

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"message": {"content": self._content}}


class FakeOpenAIResponse:
    """Stand-in for httpx2.Response with a chat-completions payload."""

    def __init__(self, content: str = "Hello", usage: dict | None = None):
        self._content = content
        self._usage = usage or {"total_tokens": 7}

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}], "usage": self._usage}


def _timeout_error() -> httpx2.ReadTimeout:
    return httpx2.ReadTimeout("timed out", request=httpx2.Request("POST", "http://example.test"))


class CaptureProvider(AIProvider):
    """Records every request it receives and answers 'ok'."""

    name = "Capture"

    def __init__(self):
        self.received: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ProviderResponse:
        self.received.append(request)
        return ProviderResponse(success=True, provider=self.name, model="m", text="ok")


class NoDefaultProvider(OpenAICompatibleProvider):
    """OpenAI-compatible adapter without a fallback base URL."""

    default_base_url = ""


# ----------------------------------------------------------------------
# 1. Provider interface
# ----------------------------------------------------------------------


def test_adapters_implement_the_provider_interface():
    """Every adapter is an AIProvider exposing name, model and capabilities."""
    providers = [
        LocalHermesProvider(HermesConfig(provider="ollama", model="m", local_model="hermes3:8b")),
        OpenRouterProvider(HermesConfig(provider="openrouter", model="m")),
        OpenAICompatibleProvider(
            HermesConfig(
                provider="openai_compatible", model="m", openai_compatible_url="https://x/v1"
            )
        ),
    ]
    for provider in providers:
        assert isinstance(provider, AIProvider)
        assert provider.name
        assert isinstance(provider.capabilities(), ModelCapabilities)
        assert provider.model


def test_capabilities_declare_only_what_adapters_honor():
    """No fabricated capabilities: vision/tool-calling/streaming stay off."""
    ollama = LocalHermesProvider(HermesConfig(provider="ollama", model="m"))
    assert ollama.capabilities() == ModelCapabilities(
        tool_calling=False,
        structured_output=True,
        vision=False,
        streaming=False,
        context_window=None,
    )

    remote = OpenAICompatibleProvider(
        HermesConfig(provider="openai_compatible", model="m", openai_compatible_url="https://x/v1")
    )
    assert remote.capabilities().structured_output is True
    assert remote.capabilities().vision is False
    assert remote.capabilities().tool_calling is False


def test_default_capabilities_declare_nothing():
    """A provider that does not override capabilities() declares nothing."""

    class SilentProvider(AIProvider):
        name = "Silent"

        def generate(self, request: ModelRequest) -> ProviderResponse:
            return ProviderResponse(success=True, provider=self.name, model="m", text="ok")

    assert SilentProvider().capabilities() == ModelCapabilities()

    # And an uninitialized manager reports the same safe default.
    assert ProviderManager().capabilities() == ModelCapabilities()


# ----------------------------------------------------------------------
# 2. Request normalization
# ----------------------------------------------------------------------


def test_task_to_request_strips_orchestration_metadata():
    """ModelRequest carries only what the model needs — never id/context."""
    task = Task(
        id="task_x",
        prompt="hi",
        task_type="chat",
        context={"key": "value"},
        instructions="be helpful",
        history=[{"role": "user", "content": "earlier"}],
        memory="remember: x",
    )
    request = task.to_request()

    assert isinstance(request, ModelRequest)
    assert request.prompt == "hi"
    assert request.instructions == "be helpful"
    assert request.history == [{"role": "user", "content": "earlier"}]
    assert request.memory == "remember: x"
    assert not hasattr(request, "id")
    assert not hasattr(request, "task_type")
    assert not hasattr(request, "context")


def test_manager_normalizes_task_to_request():
    """Whatever the orchestrator hands in, adapters receive a ModelRequest."""
    manager = ProviderManager()
    capture = CaptureProvider()
    manager.initialize(capture)

    manager.generate(Task(prompt="hello", id="task_1", context={"k": "v"}))

    assert len(capture.received) == 1
    assert isinstance(capture.received[0], ModelRequest)
    assert capture.received[0].prompt == "hello"


def test_manager_generate_without_provider_raises_clean_error():
    manager = ProviderManager()
    with pytest.raises(ProviderUnavailable):
        manager.generate(ModelRequest(prompt="hi"))


def test_with_instructions_copies_without_mutating():
    """Request copies keep the original untouched (planner helper)."""
    request = ModelRequest(prompt="hi", history=[{"role": "user", "content": "earlier"}])
    decision = request.with_instructions("Decide now.")

    assert decision.prompt == "hi"
    assert decision.instructions == "Decide now."
    assert decision.history == request.history
    assert request.instructions is None


# ----------------------------------------------------------------------
# 3. Response normalization (OpenAI-compatible wire format)
# ----------------------------------------------------------------------


def _openai_provider(config=None):
    config = config or HermesConfig(
        provider="openai_compatible",
        model="test-model",
        openai_compatible_url="https://example.com/v1",
        openai_compatible_api_key="sk-test",
    )
    return OpenAICompatibleProvider(config)


def test_openai_compatible_maps_success_and_usage(monkeypatch):
    provider = _openai_provider()
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["headers"] = kwargs["headers"]
        return FakeOpenAIResponse(content="Hi there", usage={"total_tokens": 12})

    monkeypatch.setattr(provider._client, "post", fake_post)

    response = provider.generate(ModelRequest(prompt="Say hello"))

    assert response.success is True
    assert response.provider == "OpenAI-Compatible"
    assert response.text == "Hi there"
    assert response.usage == {"total_tokens": 12}
    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == "test-model"
    assert captured["json"]["messages"] == [{"role": "user", "content": "Say hello"}]
    assert captured["json"]["stream"] is False


def test_openai_compatible_error_mapping(monkeypatch):
    """Every failure becomes a graceful ProviderResponse, never an exception."""
    provider = _openai_provider()

    def raise_status(url, **kwargs):
        request = httpx2.Request("POST", url)
        raise httpx2.HTTPStatusError(
            "Not Found", request=request, response=httpx2.Response(404, request=request)
        )

    monkeypatch.setattr(provider._client, "post", raise_status)
    response = provider.generate(ModelRequest(prompt="hi"))
    assert response.success is False
    assert "HTTP 404" in response.error


def test_openai_compatible_timeout_maps_to_error(monkeypatch):
    provider = _openai_provider()

    def raise_timeout(url, **kwargs):
        raise _timeout_error()

    monkeypatch.setattr(provider._client, "post", raise_timeout)
    response = provider.generate(ModelRequest(prompt="hi"))
    assert response.success is False
    assert response.error == "Connection timeout"


def test_openai_compatible_connection_error_maps_to_error(monkeypatch):
    provider = _openai_provider()

    def raise_connect(url, **kwargs):
        raise httpx2.ConnectError("refused")

    monkeypatch.setattr(provider._client, "post", raise_connect)
    response = provider.generate(ModelRequest(prompt="hi"))
    assert response.success is False
    assert "Connection error" in response.error


def test_openai_compatible_malformed_response_is_invalid(monkeypatch):
    provider = _openai_provider()

    class Garbage:
        def raise_for_status(self):
            pass

        def json(self):
            return {"unexpected": True}

    def fake_post(url, **kwargs):
        return Garbage()

    monkeypatch.setattr(provider._client, "post", fake_post)
    response = provider.generate(ModelRequest(prompt="hi"))
    assert response.success is False
    assert response.error == "Invalid response"


def test_openai_compatible_null_content_is_invalid(monkeypatch):
    """Some endpoints return content:null (e.g. a refusal) — never a crash."""
    provider = _openai_provider()

    class NullContent:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": None}}]}

    def fake_post(url, **kwargs):
        return NullContent()

    monkeypatch.setattr(provider._client, "post", fake_post)
    response = provider.generate(ModelRequest(prompt="hi"))
    assert response.success is False
    assert response.error == "Invalid response"


def test_openai_compatible_keyless_endpoint_sends_no_auth_header(monkeypatch):
    """Local OpenAI-compatible servers work without a key (no auth header)."""
    provider = _openai_provider(
        HermesConfig(
            provider="openai_compatible",
            model="m",
            openai_compatible_url="http://localhost:1234/v1",
            openai_compatible_api_key="",
        )
    )
    captured = {}

    def fake_post(url, **kwargs):
        captured["headers"] = kwargs["headers"]
        return FakeOpenAIResponse()

    monkeypatch.setattr(provider._client, "post", fake_post)
    response = provider.generate(ModelRequest(prompt="hi"))
    assert response.success is True
    assert "Authorization" not in captured["headers"]


def test_openai_compatible_missing_endpoint_fails_gracefully():
    """A provider with no endpoint never touches the network."""
    provider = NoDefaultProvider(
        HermesConfig(provider="openai_compatible", model="m", openai_compatible_url="")
    )
    response = provider.generate(ModelRequest(prompt="hi"))
    assert response.success is False
    assert "endpoint" in response.error.lower()


def test_openrouter_requires_api_key_and_sends_site_headers():
    """OpenRouter wiring: key required, referer/title headers attached."""
    config = HermesConfig(
        provider="openrouter",
        model="openai/gpt-5",
        openrouter_http_referer="https://sarthi.local",
        openrouter_x_title="Sarthi",
    )
    missing = OpenRouterProvider(config)
    response = missing.generate(ModelRequest(prompt="hi"))
    assert response.success is False
    assert response.error == "Missing API key"

    with_key = OpenRouterProvider(
        HermesConfig(
            provider="openrouter",
            model="openai/gpt-5",
            openrouter_api_key="or-key",
            openrouter_http_referer="https://sarthi.local",
            openrouter_x_title="Sarthi",
        )
    )
    captured = {}

    def fake_post(url, **kwargs):
        captured["headers"] = kwargs["headers"]
        return FakeOpenAIResponse()

    with_key._client.post = fake_post
    response = with_key.generate(ModelRequest(prompt="hi"))
    assert response.success is True
    assert captured["headers"]["Authorization"] == "Bearer or-key"
    assert captured["headers"]["HTTP-Referer"] == "https://sarthi.local"
    assert captured["headers"]["X-Title"] == "Sarthi"


def test_ollama_missing_url_fails_gracefully():
    provider = LocalHermesProvider(HermesConfig(provider="ollama", local_hermes_url=""))
    response = provider.generate(ModelRequest(prompt="hi"))
    assert response.success is False
    assert response.error == "Missing Ollama URL"


# ----------------------------------------------------------------------
# 4. Structured-output flags
# ----------------------------------------------------------------------


def test_ollama_json_mode_set_only_when_structured_output_requested(monkeypatch):
    provider = LocalHermesProvider(
        HermesConfig(provider="ollama", local_hermes_url="http://localhost:11434", model="m")
    )
    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        return FakeOllamaResponse()

    monkeypatch.setattr(provider._client, "post", fake_post)

    provider.generate(ModelRequest(prompt="hi"))
    assert "format" not in captured["json"]

    provider.generate(ModelRequest(prompt="hi", structured_output=True))
    assert captured["json"]["format"] == "json"


def test_openai_compatible_response_format_set_only_when_requested(monkeypatch):
    provider = _openai_provider()
    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        return FakeOpenAIResponse()

    monkeypatch.setattr(provider._client, "post", fake_post)

    provider.generate(ModelRequest(prompt="hi"))
    assert "response_format" not in captured["json"]

    provider.generate(ModelRequest(prompt="hi", structured_output=True))
    assert captured["json"]["response_format"] == {"type": "json_object"}


# ----------------------------------------------------------------------
# 5. Capability negotiation
# ----------------------------------------------------------------------


def test_manager_exposes_active_provider_capabilities():
    provider = LocalHermesProvider(HermesConfig(provider="ollama", model="m"))
    manager = ProviderManager()
    manager.initialize(provider)
    assert manager.capabilities() == provider.capabilities()
    assert manager.capabilities().structured_output is True


# ----------------------------------------------------------------------
# 6. Config-driven provider selection
# ----------------------------------------------------------------------


def test_provider_name_resolution():
    assert resolve_provider_name("ollama") == "local"
    assert resolve_provider_name("local") == "local"
    assert resolve_provider_name("local_hermes") == "local"
    assert resolve_provider_name("OpenRouter") == "openrouter"
    assert resolve_provider_name("openrouter/free") == "openrouter"
    assert resolve_provider_name("openai_compatible") == "openai_compatible"
    assert resolve_provider_name("openai-compatible") == "openai_compatible"
    assert resolve_provider_name("openai") == "openai_compatible"
    # Unknown values fall back to the safe local provider — never remote.
    assert resolve_provider_name("garbage-name") == "local"
    assert resolve_provider_name(None) == "local"


def test_build_manager_local_only():
    manager = build_provider_manager(HermesConfig(provider="ollama", model="m"))
    assert manager.primary.name == "Ollama"
    assert manager.fallback is None
    assert is_local_only(HermesConfig(provider="ollama", model="m")) is True


def test_build_manager_remote_gets_local_fallback():
    for provider_name, primary_name in [
        ("openrouter", "OpenRouter"),
        ("openai_compatible", "OpenAI-Compatible"),
    ]:
        manager = build_provider_manager(HermesConfig(provider=provider_name, model="m"))
        assert manager.primary.name == primary_name
        assert manager.fallback is not None
        assert manager.fallback.name == "Ollama"
        assert is_local_only(HermesConfig(provider=provider_name, model="m")) is False


def test_provider_status_snapshot():
    config = HermesConfig(provider="openrouter", model="openai/gpt-5")
    manager = build_provider_manager(config)
    status = provider_status(config, manager)

    assert status["provider"] == "OpenRouter"
    assert status["model"] == "openai/gpt-5"
    assert status["fallback_provider"] == "Ollama"
    assert status["configured_provider"] == "openrouter"
    assert status["capabilities"]["structured_output"] is True


# ----------------------------------------------------------------------
# 7. Tool-call normalization through the Tool Planner
# ----------------------------------------------------------------------


def test_agent_sends_decision_prompt_and_refuses_unregistered_tools():
    """The single Hermes loop offers the registered tools and refuses a
    hallucinated tool name without ever dispatching it."""
    from hermes.agent import HermesAgent
    from hermes.tool_registry import ToolRegistry

    class FakeRetriever:
        class _Context:
            text = ""

            def as_dict(self) -> dict:
                return {"sources": 0}

        def retrieve(self, query, session_id=None):
            return FakeRetriever._Context()

    captured: list = []

    def fake_generate(request):
        captured.append(request)
        if len(captured) == 1:
            return ProviderResponse(
                success=True,
                provider="Fake",
                model="m",
                text='{"tool_call": {"tool": "ghost_tool", "arguments": {}}}',
            )
        return ProviderResponse(
            success=True, provider="Fake", model="m", text="That capability is not available."
        )

    agent = HermesAgent(
        generate=fake_generate,
        tool_registry=ToolRegistry(),
        retriever=FakeRetriever(),
        fast_path=False,
    )
    result = agent.run("do the thing")

    assert captured[0].prompt == "do the thing"
    assert "Available tools" in captured[0].instructions
    # Unregistered tools are never executed — a graceful answer is returned.
    assert result["success"] is True
    assert result["text"] == "That capability is not available."
    assert result["tool_used"] is None


# ----------------------------------------------------------------------
# 8. Browser Awareness independence
# ----------------------------------------------------------------------


def test_browser_awareness_builds_provider_through_registry(monkeypatch):
    """The inspector's default provider comes from the registry, so it
    follows configuration instead of a concrete adapter import."""
    from skills.browser_awareness import hermes_inspector

    sentinel = object()
    monkeypatch.setattr("hermes.providers.registry.create_local_provider", lambda: sentinel)
    hermes_inspector._local_provider_instance = None

    assert hermes_inspector._local_provider() is sentinel


def test_create_local_provider_returns_ollama_adapter():
    """The configured local provider is the Ollama adapter (Ollama URL/model)."""
    provider = create_local_provider(
        HermesConfig(provider="ollama", local_hermes_url="http://localhost:11434", model="m")
    )
    assert isinstance(provider, LocalHermesProvider)
    assert provider.name == "Ollama"
    # Local model takes precedence over the generic model.
    assert provider.model == "hermes3:8b"


# ----------------------------------------------------------------------
# 9. /hermes/status diagnostic endpoint
# ----------------------------------------------------------------------


def test_status_endpoint_reports_active_provider(monkeypatch):
    from unittest.mock import patch

    from api import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    with patch("hermes.service.get_provider_status") as mock_status:
        mock_status.return_value = {
            "provider": "Ollama",
            "model": "hermes3:8b",
            "capabilities": {
                "tool_calling": False,
                "structured_output": True,
                "vision": False,
                "streaming": False,
                "context_window": None,
            },
            "fallback_provider": None,
            "fallback_model": None,
            "configured_provider": "ollama",
            "configured_model": "hermes3:8b",
        }
        response = client.get("/hermes/status")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["provider"] == "Ollama"
    assert data["model"] == "hermes3:8b"
    assert data["capabilities"]["structured_output"] is True
    assert data["configured_provider"] == "ollama"
