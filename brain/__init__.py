"""
Brain package for Sarthi — Core NLP pipeline.

Pipeline:
    interpreter.py  — Parse natural language into Intent
    planner.py      — Multi-step plan generation
    resolver.py     — Resolve entities via fuzzy matching (pure DI)
    executor.py     — Dispatch intents to handlers
    engine.py       — Orchestrates the full pipeline (PUBLIC API)
    intent.py       — Core Intent model
    context.py      — Pipeline runtime context
    response.py     — Standardized response model

PUBLIC API (preferred):
    from brain.engine import BrainEngine
    engine = BrainEngine()
    response = engine.process("open Chrome")

LEGACY (backward compatible):
    from brain.entity_resolver import EntityResolver
    from brain.schemas import Intent
"""

from brain.engine import BrainEngine

__all__ = ["BrainEngine"]
