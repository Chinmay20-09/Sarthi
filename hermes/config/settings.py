from dataclasses import dataclass


@dataclass
class HermesConfig:
    provider: str = "openrouter"
    model: str = "openai/gpt-5"
    temperature: float = 0.2
    timeout: float = 60.0
    sandbox_path: str = "sandbox"
    api_key: str = ""
    http_referer: str = ""
    x_title: str = "Sarthi"
