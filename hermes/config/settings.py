from dataclasses import dataclass


@dataclass
class HermesConfig:
    # One authoritative default: local-first (Ollama, no cloud). Remote
    # providers (openrouter / openai_compatible / openai) are opt-in via
    # HERMES_PROVIDER and get an automatic local fallback when selected.
    provider: str = "local"
    model: str = "openai/gpt-5"
    temperature: float = 0.2
    timeout: float = 60.0
    sandbox_path: str = "sandbox"
    # OpenRouter settings (only used when provider=openrouter)
    openrouter_api_key: str = ""
    openrouter_url: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_http_referer: str = ""
    openrouter_x_title: str = "Sarthi"
    # Generic OpenAI-compatible endpoint (provider=openai_compatible or openai).
    # Points at OpenAI by default; point it at any /v1-compatible endpoint
    # (LM Studio, vLLM, Together, ...) to use that service instead.
    openai_compatible_url: str = "https://api.openai.com/v1"
    openai_compatible_api_key: str = ""
    # Local Hermes settings (Ollama)
    local_hermes_url: str = "http://localhost:11434"
    local_hermes_api_key: str = ""
    # Local model name as installed in Ollama (distinct from the OpenRouter model)
    local_model: str = "hermes3:8b"
    # CPU-only inference is slow — default 180s (3x the base timeout)
    local_timeout: float = 180.0
    # legacy (falls back for providers without their own key field)
    api_key: str = ""
