"""
Natural Language Processor skill — Sarthi's conversational fallback.

Holds a normal conversation like a plain AI. It NEVER fetches or executes
tools: it asks the model directly for a reply (primary provider, local
fallback) through hermes.service.chat, which deliberately skips the tool
planner.

ARCHITECTURE:
    - Registered LAST (fallback=True). The Brain's executor sorts fallback
      skills to the end, so every real tool/skill gets the first chance at
      an intent; this skill only answers what nobody else handled.
    - Owns conversational intents: action "unknown" (no action word matched,
      confidence 0.0) and open questions (what/how/why/who/when/where).
      Imperative commands (open, check, scan, ...) are left alone so their
      skills surface their own errors or prompts.
    - The reply is produced by Hermes in plain chat mode — no tools, no
      registry, no tool bridge. The task is still saved to the sandbox so
      the conversation is referenceable like every other Hermes execution.
"""

import logging
from typing import Any

from brain.intent import Intent
from skills.base import BaseSkill

logger = logging.getLogger(__name__)

# Conversational actions this skill owns. "unknown" is what the interpreter
# produces when no action keyword matched (pure chat, confidence 0.0).
CONVERSATION_ACTIONS = {"unknown", "what", "how", "why", "who", "when", "where"}


class NaturalLanguageProcessorSkill(BaseSkill):
    """Holds a normal conversation; the last-resort fallback for Sarthi."""

    name = "Natural Language Processor"
    description = "Holds a normal conversation like a plain AI. Fallback when no tool can handle the request."
    version = "1.0.0"
    # Tried last by the Brain's executor — real tools/skills go first.
    fallback = True

    def execute(self, intent: Intent) -> dict[str, Any]:
        """
        Reply conversationally when no other skill handled the intent.

        Args:
            intent: Parsed intent from the brain pipeline.

        Returns:
            Dict with the conversational reply in result.message, or a
            graceful handled error when the language model is unreachable.
        """
        action = (intent.action or "").lower()

        # Not ours — leave imperative commands to their skills.
        if action not in CONVERSATION_ACTIONS:
            return {
                "success": False,
                "status": "unknown",
                "error": f"Unknown command: {intent.action} {intent.target}",
            }

        message = self._user_message(intent)

        try:
            from hermes.service import chat

            response = chat(message)
        except Exception as e:  # never leak internals upward
            logger.warning("Natural Language Processor could not reach Hermes: %s", e)
            return {
                "success": False,
                "status": "error",
                "handled": True,
                "error": "I couldn't reach my language model right now. Check that Ollama is running.",
            }

        if response.success:
            return {
                "success": True,
                "status": "executed",
                "result": {
                    # source="nlp" lets the UI badge replies as the
                    # conversational fallback rather than a generic Sarthi run.
                    "source": "nlp",
                    "message": response.text,
                    "provider": response.provider,
                    "model": response.model,
                },
            }

        # Model call failed but the skill owns the conversation — surface a
        # graceful, handled error instead of falling through to no_handler.
        return {
            "success": False,
            "status": "error",
            "handled": True,
            "error": response.error or "I couldn't think of an answer right now.",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _user_message(self, intent: Intent) -> str:
        """The user's original text (raw_text), or a reconstruction."""
        raw = (intent.raw_text or "").strip()
        if raw:
            return raw
        parts = [p for p in (intent.action, intent.target) if p]
        return " ".join(parts) if parts else "Hello"
