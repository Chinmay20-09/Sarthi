"""Deterministic, minimal, persisted Sarthi mood state."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

MOODS = {"happy", "curious", "calm", "focused", "sleepy", "concerned", "playful", "neutral"}
MOOD_MEMORY_KEY = "personality:simulated_mood"
DEFAULT_MOOD_DECAY = timedelta(hours=2)
_CONFIG: tuple[bool, timedelta] | None = None


def _personality_config() -> tuple[bool, timedelta]:
    """Read small optional settings from the same Backend/.env file."""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    except ImportError:
        pass
    persist = os.getenv("SARTHI_PERSONALITY_MOOD_PERSISTENCE", "true").lower() != "false"
    try:
        decay = timedelta(
            minutes=max(1, int(os.getenv("SARTHI_PERSONALITY_MOOD_DECAY_MINUTES", "120")))
        )
    except ValueError:
        decay = DEFAULT_MOOD_DECAY
    _CONFIG = (persist, decay)
    return _CONFIG


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SarthiMood:
    mood: str
    updated_at: str


class SarthiMoodEngine:
    """Small deterministic state machine backed by existing KnowledgeMemory."""

    def __init__(self, memory=None, *, persist: bool | None = None, decay: timedelta | None = None):
        configured_persist, configured_decay = _personality_config()
        if memory is None:
            from knowledge.memory import get_memory

            memory = get_memory()
        self._memory = memory
        self._persist = configured_persist if persist is None else persist
        self._decay = configured_decay if decay is None else decay

    def current(self, now: datetime | None = None) -> SarthiMood:
        raw = self._memory.recall_long(MOOD_MEMORY_KEY) if self._persist else None
        try:
            data = json.loads(raw) if raw else {}
            mood = data.get("mood")
            updated = datetime.fromisoformat(data.get("updated_at", ""))
            if mood in MOODS and (now or _now()) - updated > self._decay:
                return self._save("calm", now=now)
            if mood in MOODS:
                return SarthiMood(mood, updated.isoformat())
        except (TypeError, ValueError):
            pass
        return self._save("neutral", now=now)

    def update(
        self,
        *,
        user_mood: str = "unknown",
        message: str = "",
        outcome: str | None = None,
        task_active: bool = False,
        now: datetime | None = None,
    ) -> SarthiMood:
        """Apply one controlled transition; neutral turns preserve the mood."""
        current = self.current(now=now)
        if outcome == "success":
            next_mood = "happy"
        elif outcome == "failure":
            next_mood = "concerned"
        elif task_active:
            next_mood = "focused"
        elif user_mood in {"sad", "frustrated", "stressed"}:
            next_mood = "concerned"
        elif user_mood == "tired":
            next_mood = "calm"
        elif user_mood == "happy":
            next_mood = "happy"
        elif user_mood == "playful":
            next_mood = "playful"
        elif user_mood == "confused":
            next_mood = "curious"
        elif re_seeking_curiosity(message):
            next_mood = "curious"
        else:
            next_mood = current.mood
        return self._save(next_mood, now=now) if next_mood != current.mood else current

    def _save(self, mood: str, now: datetime | None = None) -> SarthiMood:
        state = SarthiMood(mood, (now or _now()).isoformat())
        try:
            if self._persist:
                self._memory.remember_long(MOOD_MEMORY_KEY, json.dumps(asdict(state)))
        except Exception:
            pass  # mood is optional; chat must degrade gracefully
        return state


def re_seeking_curiosity(message: str) -> bool:
    lowered = (message or "").lower()
    return any(lowered.startswith(prefix) for prefix in ("why ", "how does ", "what causes ", "i wonder "))
