"""
skills/browser_awareness/hermes_inspector.py

Hermes as the *Browser Awareness Agent* — it observes and recommends,
it never controls the browser.

Given the user objective and the compact page snapshot it must answer
one question: "What is on this page, and what single action (if any)
should the Brain take next?" Its answer is validated against the strict
InspectionResult schema before the Brain may act on it.

The call goes straight to the local Hermes provider (Ollama) — the same
pattern as ai_chain/awareness.py — so no sandbox record is created per
inspection and no cloud credits are spent unless configured otherwise.
"""

from __future__ import annotations

import json
import re

from utils.logger import get_logger

from .page_snapshot import snapshot_for_hermes
from .schemas import InspectionResult, PageSnapshot

logger = get_logger(__name__)

# Local inference on CPU is slow — keep the snapshot + prompt small.
MAX_SNAPSHOT_CHARS = 6000

HERMES_PROMPT = """\
You are the Browser Awareness Agent of a desktop assistant. You only observe
pages and recommend ONE next action. You never control the browser yourself.

USER OBJECTIVE:
{objective}

{snapshot}

Decide what is present on the page and how the objective can be reached.
Reply with ONLY a JSON object, no prose, with this exact shape:
{{
  "status": "continue" | "done" | "blocked",
  "understanding": "what you see and how it relates to the objective",
  "action": {{
    "type": "navigate|click|type|select|check|uncheck|submit|scroll",
    "element_id": "<id of an element listed above, or null>",
    "value": "<text to type / option to select, or null>",
    "url": "<http(s) url for navigate, else null>",
    "requires_confirmation": false,
    "rationale": "why this action"
  }},
  "message": "optional note to the user"
}}

Rules:
- status "done" when the objective is already satisfied on this page
  (action must be null).
- status "blocked" when the objective cannot be reached from this page
  (login wall, missing feature, error page) — action must be null and
  message must explain clearly to the user.
- status "continue" with exactly one action otherwise.
- reference ONLY element ids that are listed above (never invent ids or
  selectors). For type/select/check/uncheck/submit the element must match
  the action (e.g. type only into inputs/textareas).
- navigate only to http(s) URLs. Never fabricate URLs from memory —
  only use hrefs visible on the page, or keep it to the same site.
- do NOT click submit-like buttons that purchase, send messages, delete
  accounts or otherwise cause irreversible effects without setting
  requires_confirmation to true.
"""


class HermesInspector:
    """Asks the local model to observe a page snapshot and returns JSON."""

    def __init__(self, provider=None):
        """
        Args:
            provider: object with generate(task) -> ProviderResponse.
                      Defaults to the local Ollama Hermes provider.
        """
        self._provider = provider

    def observe(self, objective: str, snapshot: PageSnapshot) -> InspectionResult:
        """Return Hermes' strict observation of the snapshot."""
        provider = self._provider or _local_provider()
        prompt = HERMES_PROMPT.format(
            objective=(objective or "").strip() or "(describe this page)",
            snapshot=snapshot_for_hermes(snapshot)[:MAX_SNAPSHOT_CHARS],
        )

        try:
            from hermes.models import Task

            response = provider.generate(Task(prompt=prompt, task_type="browser_awareness"))
        except Exception as exc:
            logger.warning("[HERMES] browser observation unavailable: %s", exc)
            return InspectionResult(
                status="blocked",
                message="The awareness model is not reachable right now — "
                "make sure the local model is running.",
            )

        if not response.success or not response.text:
            return InspectionResult(
                status="blocked",
                message="The awareness model could not inspect the page.",
            )

        return _parse_observation(response.text)


def _parse_observation(text: str) -> InspectionResult:
    """Strictly parse + validate the model's JSON answer.

    Garbage or schema-violating output becomes a blocked result — a
    malformed model answer must never reach the executor.
    """
    raw = _extract_json(text)
    if raw is None:
        logger.warning("[HERMES] observation was not valid JSON")
        return InspectionResult(
            status="blocked",
            message="The awareness model returned an unreadable answer — "
            "nothing was executed.",
        )
    try:
        return InspectionResult.model_validate(raw)
    except Exception as exc:
        logger.warning("[HERMES] observation failed schema validation: %s", exc)
        return InspectionResult(
            status="blocked",
            message="The awareness model returned a malformed plan — "
            "nothing was executed.",
        )


def _extract_json(text: str) -> dict | None:
    """Pull a JSON object out of a model reply (code fences tolerated)."""
    cleaned = (text or "").strip()
    # Strip ```json ... ``` fences if the model wrapped the answer.
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Model added prose before/after the object — try the first {...}
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


_local_provider_instance = None


def _local_provider():
    """Cached local Ollama provider (shared client).

    Built through the provider registry so Browser Awareness depends on the
    configured Hermes provider stack, never on a concrete adapter import.
    """
    global _local_provider_instance
    if _local_provider_instance is None:
        from hermes.providers.registry import create_local_provider

        _local_provider_instance = create_local_provider()
    return _local_provider_instance
