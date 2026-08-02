from dataclasses import dataclass


@dataclass
class HermesConfig:
    model = "hermes3:8b"
    sandbox_dir = "sandbox"
    temperature = 0.2