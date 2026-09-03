"""
ai_chain/awareness.py

Browser awareness for the AI chain.

The robot reads AI replies by Ctrl+A / Ctrl+C on the page and taking the
text after the sent prompt. That heuristic is blind: when the copy comes
back as page chrome (sidebars, menus, "New chat" buttons) — or when the
reply never rendered — it cannot tell, and the "reply" saved is garbage.

The module's *screen-state classifier* (screen.py) already filters the
deterministic cases — login walls, new-chat landings, loading pages and
element fragments are recognised from the copy and never get this far.
This module handles the ambiguous middle with the **local Hermes model**
(Ollama): a transcript that really looks like a conversation but that
the heuristic failed to parse is sent to the model with an extraction
instruction, and the model's answer becomes the reply. If the model also
sees no real reply (login wall, wrong page, loading), it says so and the
step fails with a clear message instead of storing chrome.

The call goes straight to LocalHermesProvider (never through the
orchestrator), so no sandbox record is created per extraction and no
cloud API credits are spent. Everything is wrapped: if the local model is
not available the driver simply keeps the heuristic result.
"""

from __future__ import annotations

from utils.logger import get_logger

from .parsing import prompt_present

logger = get_logger(__name__)

NO_REPLY_MARKER = "<no reply>"

# The model only needs the relevant part of the copy; capping keeps the
# local inference fast (CPU Ollama) and the prompt well-formed.
MAX_TRANSCRIPT_CHARS = 8000
MAX_PROMPT_CHARS = 500

AWARENESS_PROMPT = """\
You are the browser-awareness module of a desktop robot driving an AI website.
Below is the full text that was copied from the page (Ctrl+A / Ctrl+C) and the
exact prompt the robot sent. The copy often includes navigation menus,
sidebars, buttons and other page chrome.

Extract ONLY the AI assistant's reply to the sent prompt:
- Return the reply verbatim, keeping its line breaks. No quotes, no preamble,
  no "The reply is: ...".
- If the page shows no assistant reply (login wall, loading page, error page,
  or only menus/sidebar text), reply with exactly: {no_reply}

PROMPT SENT TO THE AI:
{prompt}

PAGE TRANSCRIPT:
{transcript}
"""


def needs_awareness(reply: str, transcript: str, prompt: str) -> bool:
    """True when the heuristic result should be double-checked by the model.

    The heuristic trusts its result only when it found the sent prompt in
    the transcript AND extracted non-empty text after it. Otherwise the
    "reply" is likely page chrome or nothing — send it to awareness.
    """
    if not reply.strip():
        return True
    return not prompt_present(transcript, prompt)


class AwarenessExtractor:
    """Interprets a copied transcript with the local Hermes model."""

    def __init__(self, provider=None):
        """
        Args:
            provider: A provider with generate(task) -> ProviderResponse.
                      Defaults to the local Ollama Hermes provider.
        """
        self._provider = provider

    def extract(self, transcript: str, prompt: str) -> str:
        """
        Ask the model to pull the assistant's reply out of the transcript.

        Returns:
            The extracted reply, or "" when the model saw no real reply or
            awareness is unavailable (the driver keeps its heuristic result).
        """
        try:
            from hermes.models import Task

            task_prompt = AWARENESS_PROMPT.format(
                no_reply=NO_REPLY_MARKER,
                prompt=(prompt or "")[:MAX_PROMPT_CHARS],
                transcript=(transcript or "")[:MAX_TRANSCRIPT_CHARS],
            )
            provider = self._provider or _local_provider()
            response = provider.generate(Task(prompt=task_prompt))
        except Exception as exc:
            logger.warning("Browser awareness unavailable: %s", exc)
            return ""

        if not response.success or not response.text:
            logger.info("Browser awareness model could not interpret the transcript")
            return ""

        return _clean_model_reply(response.text)


def _clean_model_reply(text: str) -> str:
    """Strip the no-reply marker and empty noise from the model's answer."""
    reply = (text or "").strip()
    if not reply:
        return ""
    if reply.lower() == NO_REPLY_MARKER:
        return ""
    if NO_REPLY_MARKER in reply:
        # The model echoed the marker but also returned something — keep
        # the non-marker lines.
        reply = "\n".join(
            line for line in reply.splitlines()
            if line.strip().lower() != NO_REPLY_MARKER
        ).strip()
    return reply


_local_provider_instance = None


def _local_provider():
    """The cached local Ollama Hermes provider (shared httpx client)."""
    global _local_provider_instance
    if _local_provider_instance is None:
        from hermes.config.loader import ConfigLoader
        from hermes.providers.local_provider import LocalHermesProvider

        _local_provider_instance = LocalHermesProvider(ConfigLoader().load())
    return _local_provider_instance


# Convenience: build one shared extractor for the driver.
def default_extractor() -> AwarenessExtractor:
    """An AwarenessExtractor wired to the local Hermes model."""
    return AwarenessExtractor(provider=_local_provider())
