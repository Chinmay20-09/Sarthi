from dataclasses import dataclass, field


@dataclass
class Command:

    action: str

    target: str

    parameters: dict = field(default_factory=dict)

    confidence: float = 1.0