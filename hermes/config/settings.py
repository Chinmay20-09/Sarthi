from dataclasses import dataclass


@dataclass
class HermesConfig:
    provider: str = "openrouter/free"
    model: str = "openai/gpt-5"
    temperature: float = 0.2
    timeout: float = 60.0
    sandbox_path: str = "sandbox"
    # OpenRouter settings
    openrouter_api_key: str = ""
    openrouter_url: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_http_referer: str = ""
    openrouter_x_title: str = "Sarthi"
    # Local Hermes settings (Ollama)
    local_hermes_url: str = "http://localhost:11434"
    local_hermes_api_key: str = ""
    # legacy
    api_key: str = ""
