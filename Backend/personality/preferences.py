"""Explicit and repeated preference learning on existing KnowledgeMemory."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

PREFERENCE_PREFIX = "personality:preference:"
_SENSITIVE = re.compile(
    r"\b(password|passcode|secret|api\s*key|access\s*token|credential|social security|credit card|bank account)\b",
    re.I,
)
_EXPLICIT = re.compile(
    r"\b(?:i prefer|i'd prefer|i would prefer|please (?:keep|use|give me)|from now on,? use)\s+(.{2,120})",
    re.I,
)
_CORRECTION = re.compile(r"\b(actually|instead|i changed my mind|correction|no,? i prefer)\b", re.I)
_FEEDBACK = {
    "concise": re.compile(r"\b(too long|shorter please|keep it short|be concise|less detail)\b", re.I),
    "detailed": re.compile(r"\b(more detail|explain more|show more steps|too brief)\b", re.I),
    "examples": re.compile(r"\b(add an example|more examples|show me an example)\b", re.I),
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class PreferenceService:
    """Stores namespaced metadata in knowledge_memory; no second database."""

    def __init__(self, memory=None):
        if memory is None:
            from knowledge.memory import get_memory

            memory = get_memory()
        self._memory = memory
        self._observations: dict[str, int] = {}

    def observe(self, text: str) -> dict | None:
        """Learn explicit safe preferences or repeated communication feedback."""
        text = (text or "").strip()
        if not text or _SENSITIVE.search(text):
            return None
        explicit = _EXPLICIT.search(text)
        if explicit:
            value = explicit.group(1).strip(" .!\t\n")
            key = self._classify(text, value)
            return self._save(key, value, source="explicit", confidence=1.0, confirmed=True,
                              allow_replace=bool(_CORRECTION.search(text)))

        for label, pattern in _FEEDBACK.items():
            if pattern.search(text):
                key = "communication.response_style"
                self._observations[label] = self._observations.get(label, 0) + 1
                if self._observations[label] < 3:
                    continue
                return self._save(key, label, source="repeated_feedback", confidence=0.65,
                                  confirmed=False, allow_replace=False)
        return None

    @staticmethod
    def _classify(text: str, value: str) -> str:
        lowered = f"{text} {value}".lower()
        if any(word in lowered for word in ("concise", "short", "brief", "length", "answer", "response")) and any(
            word in lowered for word in ("concise", "short", "brief", "detailed", "answer", "response")
        ):
            return "communication.response_style"
        if any(word in lowered for word in ("technical", "jargon", "beginner", "detail")):
            return "communication.technical_depth"
        if "example" in lowered:
            return "communication.examples"
        if any(word in lowered for word in ("python", "editor", "code", "debug")):
            return "coding.workflow"
        return "communication.preference"

    def _save(self, key: str, value: str, *, source: str, confidence: float,
              confirmed: bool, allow_replace: bool) -> dict | None:
        memory_key = PREFERENCE_PREFIX + key
        old_raw = self._memory.recall_long(memory_key)
        old = self._decode(old_raw)
        if old and old.get("confirmed") and not allow_replace:
            return old
        now = _timestamp()
        record = {
            "key": key,
            "value": value,
            "source": source,
            "confidence": confidence,
            "confirmed": confirmed,
            "status": "active",
            "scope": "user",
            "created_at": old.get("created_at", now) if old else now,
            "updated_at": now,
        }
        if self._memory.remember_long(memory_key, json.dumps(record, ensure_ascii=False)):
            return record
        return None

    def list(self, include_rejected: bool = False) -> list[dict]:
        try:
            rows = self._memory.list_memories(key_prefix=PREFERENCE_PREFIX)
        except Exception:
            return []
        records = []
        for row in rows:
            if not str(row.get("key", "")).startswith(PREFERENCE_PREFIX):
                continue
            record = self._decode(row.get("value"))
            if record and (include_rejected or record.get("status") == "active"):
                records.append(record)
        return records

    def relevant(self, message: str, limit: int = 3) -> list[dict]:
        """Return a small relevant set; communication preferences always apply."""
        words = set(re.findall(r"[a-z]{3,}", (message or "").lower()))
        ranked = []
        for record in self.list():
            key = record.get("key", "")
            if key.startswith("communication."):
                score = 1
            else:
                terms = set(
                    re.findall(
                        r"[a-z]{3,}",
                        f"{key.replace('.', ' ')} {record.get('value', '')}".lower(),
                    )
                )
                score = len(words & terms)
            if score:
                ranked.append((score, record))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [row for _, row in ranked[:limit]]

    def reject(self, key: str) -> bool:
        key = key.removeprefix(PREFERENCE_PREFIX).removeprefix("preference:")
        memory_key = PREFERENCE_PREFIX + key
        old = self._decode(self._memory.recall_long(memory_key))
        if not old:
            return False
        old["status"] = "rejected"
        old["updated_at"] = _timestamp()
        return bool(self._memory.remember_long(memory_key, json.dumps(old, ensure_ascii=False)))

    @staticmethod
    def _decode(raw) -> dict | None:
        try:
            item = json.loads(raw) if isinstance(raw, str) else None
            return item if isinstance(item, dict) else None
        except (TypeError, ValueError):
            return None
