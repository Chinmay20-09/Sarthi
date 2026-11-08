"""Predefined local inference tiers backed by the Phase 2A benchmark models."""

MODEL_PROFILES = {
    "low": {"model": "hermes3:3b", "num_ctx": 2048},
    "medium": {"model": "hermes3:8b-llama3.1-q3_K_M", "num_ctx": 2048},
    "high": {"model": "hermes3:8b", "num_ctx": 2048},
}
DEFAULT_MODEL_PROFILE = "low"
