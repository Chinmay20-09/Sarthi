from pathlib import Path


def ensure_sandbox():
    Path("sandbox").mkdir(exist_ok=True)