"""
Bounded Task Agent — the Hermes execution loop for complex tasks (Phase 3d).

HERMES THINKS. SARTHI EXECUTES.

Flow for one complex query:

    1. Deterministic fast path first — the brain pipeline (interpreter →
       resolver → executor) gets the first chance, so a wrong "complex"
       verdict from the router costs nothing when a skill can do the job.
    2. Retrieval — the hybrid Retriever pulls bounded context from the
       existing Sarthi stores (.db, knowledge, sandbox, session history).
    3. Bounded reasoning loop — the model decides: final answer OR one
       validated structured tool call. Tool calls pass the Phase 3c
       validator BEFORE the registry dispatches anything. The model sees
       the tool result and decides again, until it answers, the iteration
       cap is reached, or the time budget runs out.

The loop is bounded three ways:
    - MAX iterations (model turns that may request tools)
    - a wall-clock budget checked before every model/tool step
    - the registry itself (unknown tools never execute, tools never raise)

Everything is dependency-injected for testability: the model is a
``generate`` callable, tools live in a ToolRegistry, the deterministic
pipeline is a ``fast_path`` callable, and retrieval/sandbox are the shared
Retriever/TaskSandbox singletons by default.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from hermes.config.loader import ConfigLoader
from hermes.models import Task
from hermes.providers.base import ProviderResponse
from hermes.retriever import Retriever
from hermes.sandbox import TaskSandbox
from hermes.tool_planner import (
    build_decision_instructions,
    build_followup_instructions,
    parse_tool_call,
)
from hermes.tool_registry import ToolRegistry, get_tool_registry
from hermes.validator import validate_tool_call

logger = logging.getLogger(__name__)

# Fallback bounds when no config is available (tests, embedding callers).
DEFAULT_MAX_ITERATIONS = 5
DEFAULT_AGENT_TIMEOUT = 300.0  # seconds


class HermesAgent:
    """Runs one bounded Hermes task: think, retrieve, call tools, answer.

    Args:
        generate: Callable(Task) -> ProviderResponse. The model boundary —
            typically the orchestrator's ``_generate_with_fallback``.
        tool_registry: Registry of tools the model may request (defaults to
            the global registry).
        retriever: Hybrid retriever (defaults to a sandbox-backed Retriever).
        sandbox: TaskSandbox the run is persisted to (None disables saving).
        fast_path: Callable(str) -> dict | None. The deterministic brain
            pipeline. None (or a None return) skips the fast path. Default
            wires Sarthi's BrainEngine lazily.
        max_iterations: Cap on tool-requesting model turns.
        timeout_seconds: Wall-clock budget for the whole task.
    """

    def __init__(
        self,
        generate: Callable[[Task], ProviderResponse] | None = None,
        tool_registry: ToolRegistry | None = None,
        retriever: Retriever | None = None,
        sandbox: TaskSandbox | None = None,
        fast_path: Callable[[str], dict | None] | None = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        timeout_seconds: float = DEFAULT_AGENT_TIMEOUT,
    ) -> None:
        self._generate = generate
        self._tool_registry = tool_registry
        self._retriever = retriever
        self._sandbox = sandbox
        self._fast_path = fast_path or _default_fast_path
        self._max_iterations = max(1, int(max_iterations))
        # Floor of 1ms — a zero/negative budget means "do not run the loop".
        self._timeout_seconds = max(0.001, float(timeout_seconds))

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, query: str, session_id: str | None = None) -> dict[str, Any]:
        """Execute one complex query through the bounded agent loop.

        Returns a plain dict (API-friendly):
            {success, text, tool_used, iterations, duration_ms, timed_out,
             route, reason, provider, model, trace, error}
        """
        started = time.perf_counter()
        trace: list[dict[str, Any]] = []
        query = (query or "").strip()

        if not query:
            return self._final(
                success=False,
                text="Please enter a command.",
                trace=trace,
                started=started,
                iterations=0,
                timed_out=False,
                reason="empty_input",
                provider="Hermes",
                model="",
                tool_used=None,
                query_for_sandbox="",
            )

        # --- 1. deterministic fast path (cheap safety net) -----------------
        fast = self._try_fast_path(query, trace)
        if fast is not None:
            return self._final(
                success=True,
                text=fast,
                trace=trace,
                started=started,
                iterations=0,
                timed_out=False,
                reason="deterministic_pipeline",
                provider="Sarthi",
                model="",
                tool_used=None,
                query_for_sandbox=query,
            )

        # --- 2. retrieval ---------------------------------------------------
        context_text = self._retrieve(query, session_id, trace)

        # --- 3. bounded reasoning loop --------------------------------------
        response = self._loop(query, context_text, session_id, trace)

        return self._final(query_for_sandbox=query, trace=trace, started=started, **response)

    # ------------------------------------------------------------------
    # Fast path
    # ------------------------------------------------------------------

    def _try_fast_path(self, query: str, trace: list[dict[str, Any]]) -> str | None:
        """Give the deterministic pipeline first crack; None = not handled.

        Only a fully successful, non-conversational result short-circuits:
        the NLP fallback (source == "nlp") and skill refusals fall through
        to the agent loop, which is the whole point of Hermes.
        """
        if self._fast_path is None:
            return None
        try:
            result = self._fast_path(query)
        except Exception as e:  # a broken skill must not kill the agent
            logger.warning("agent: fast path failed: %s", e)
            trace.append({"step": "fast_path", "success": False, "error": str(e)})
            return None

        handled = (
            isinstance(result, dict)
            and result.get("success") is True
            and result.get("status") in ("executed", "completed")
            and not (isinstance(result.get("result"), dict) and result["result"].get("source") == "nlp")
        )
        trace.append(
            {
                "step": "fast_path",
                "success": bool(handled),
                "status": result.get("status") if isinstance(result, dict) else None,
            }
        )
        if handled:
            text = result.get("text") or ""
            if not text and isinstance(result.get("result"), dict):
                text = result["result"].get("message", "")
            return text or "Done."
        return None

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def _retrieve(self, query: str, session_id: str | None, trace: list[dict[str, Any]]) -> str:
        retriever = self._retriever
        if retriever is None:
            retriever = Retriever(sandbox=self._sandbox)
        try:
            context = retriever.retrieve(query, session_id=session_id)
        except Exception as e:  # retrieval must never kill the task
            logger.warning("agent: retrieval failed: %s", e)
            trace.append({"step": "retrieval", "success": False, "error": str(e)})
            return ""

        trace.append({"step": "retrieval", "success": True, **context.as_dict()})
        return context.text

    # ------------------------------------------------------------------
    # The bounded loop
    # ------------------------------------------------------------------

    def _loop(
        self,
        query: str,
        context_text: str,
        session_id: str | None,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        registry = self._tool_registry or get_tool_registry()
        generate = self._generate or self._default_generate
        deadline = time.monotonic() + self._timeout_seconds
        history = self._session_history(session_id)

        tools = registry.list_tools()
        instructions = build_decision_instructions(query, tools)
        if context_text:
            instructions += (
                "\n\nRetrieved Sarthi context (may help; ignore if irrelevant):\n"
                f"{context_text}"
            )

        last_response: ProviderResponse | None = None
        tool_used: str | None = None
        iterations = 0

        while iterations <= self._max_iterations:
            if time.monotonic() >= deadline:
                return self._timeout_result(trace, tool_used, iterations, last_response)

            task = Task(
                prompt=query,
                task_type="agent",
                instructions=instructions,
                history=history,
            )
            try:
                response = generate(task)
            except Exception as e:
                logger.error("agent: model call failed: %s", e)
                return {
                    "success": False,
                    "text": "I couldn't reach my language model right now.",
                    "error": "model unavailable",
                    "tool_used": tool_used,
                    "iterations": iterations,
                    "timed_out": False,
                    "reason": "model_error",
                    "provider": "Hermes",
                    "model": "",
                }
            last_response = response
            trace.append(
                {
                    "step": "model",
                    "iteration": iterations,
                    "provider": response.provider,
                    "model": response.model,
                    "success": response.success,
                    "text": response.text,
                    "error": response.error,
                }
            )

            if not response.success:
                return {
                    "success": False,
                    "text": response.error or "I couldn't complete that request.",
                    "error": response.error,
                    "tool_used": tool_used,
                    "iterations": iterations,
                    "timed_out": False,
                    "reason": "model_error",
                    "provider": response.provider,
                    "model": response.model,
                }

            decision = parse_tool_call(response.text)
            if decision is None:
                # Plain answer — task complete.
                return {
                    "success": True,
                    "text": response.text,
                    "tool_used": tool_used,
                    "iterations": iterations,
                    "timed_out": False,
                    "reason": "final_answer",
                    "provider": response.provider,
                    "model": response.model,
                }

            if iterations >= self._max_iterations:
                break  # cap reached — no further tool execution

            if time.monotonic() >= deadline:
                return self._timeout_result(trace, tool_used, iterations, last_response)

            # --- validate BEFORE dispatch (Phase 3c gate) ----------------
            verdict = validate_tool_call(
                decision, is_registered=lambda name: registry.get(name) is not None
            )
            trace.append(
                {
                    "step": "validation",
                    "tool": decision.get("tool"),
                    "valid": verdict.valid,
                    "reason": verdict.reason,
                    "errors": verdict.errors,
                }
            )
            if not verdict.valid:
                # Feed the refusal back once; the model may correct itself.
                instructions = (
                    f'Your previous tool call was refused ({verdict.reason}): '
                    f"{verdict.message}\nRespond to the user helpfully, or "
                    "issue one corrected tool call."
                )
                iterations += 1
                continue

            # --- execute the tool ----------------------------------------
            tool = decision["tool"]
            arguments = decision.get("arguments", {})
            tool_used = tool
            if time.monotonic() >= deadline:
                return self._timeout_result(trace, tool_used, iterations, last_response)

            result = registry.execute(tool, arguments)
            trace.append(
                {
                    "step": "tool_result",
                    "tool": tool,
                    "success": result.success,
                    "result": result.result,
                    "error": result.error,
                }
            )

            instructions = build_followup_instructions(query, tool, result)
            iterations += 1

        # Iteration cap reached — stop gracefully.
        logger.warning("agent: iteration cap (%d) reached", self._max_iterations)
        text = "I needed too many steps to finish that. Please break it into smaller requests."
        if last_response is not None and last_response.text:
            text = last_response.text
        return {
            "success": True,
            "text": text,
            "tool_used": tool_used,
            "iterations": iterations,
            "timed_out": False,
            "reason": "iteration_cap",
            "provider": last_response.provider if last_response else "Hermes",
            "model": last_response.model if last_response else "",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _timeout_result(
        trace: list[dict[str, Any]],
        tool_used: str | None,
        iterations: int,
        last_response: ProviderResponse | None,
    ) -> dict[str, Any]:
        logger.warning("agent: time budget exhausted after %d iterations", iterations)
        return {
            "success": False,
            "text": "That task took too long. Please try a smaller request.",
            "error": "timeout",
            "tool_used": tool_used,
            "iterations": iterations,
            "timed_out": True,
            "reason": "timeout",
            "provider": last_response.provider if last_response else "Hermes",
            "model": last_response.model if last_response else "",
        }

    @staticmethod
    def _session_history(session_id: str | None) -> list[dict] | None:
        if not session_id:
            return None
        try:
            from hermes.conversation import get_conversation_store

            return get_conversation_store().get_history(session_id)
        except Exception:
            return None

    def _default_generate(self, task: Task) -> ProviderResponse:
        """Route model calls through the orchestrator (primary + fallback)."""
        from hermes.service import get_orchestrator

        return get_orchestrator()._generate_with_fallback(task)

    def _final(self, **kwargs: Any) -> dict[str, Any]:
        """Assemble the public result dict and persist the run (best-effort)."""
        trace = kwargs.pop("trace")
        started = kwargs.pop("started")
        query = kwargs.pop("query_for_sandbox", "")
        duration_ms = (time.perf_counter() - started) * 1000
        result = {
            "success": kwargs.get("success", False),
            "text": kwargs.get("text", ""),
            "tool_used": kwargs.get("tool_used"),
            "iterations": kwargs.get("iterations", 0),
            "duration_ms": round(duration_ms, 1),
            "timed_out": kwargs.get("timed_out", False),
            "route": "hermes",
            "reason": kwargs.get("reason", ""),
            "provider": kwargs.get("provider", ""),
            "model": kwargs.get("model", ""),
            "trace": trace,
            "error": kwargs.get("error"),
        }
        self._persist(query, result)
        return result

    def _persist(self, query: str, result: dict[str, Any]) -> None:
        """Save the run to the sandbox (best-effort, never raises)."""
        if self._sandbox is None or not query:
            return
        try:
            task = Task(
                id=f"agent_{uuid4().hex[:6]}",
                prompt=query,
                task_type="agent",
            )
            response = ProviderResponse(
                success=result["success"],
                provider=result["provider"] or "Hermes",
                model=result["model"],
                text=result["text"],
                tool_used=result.get("tool_used"),
                error=result.get("error"),
            )
            self._sandbox.save(
                task,
                response,
                duration_ms=result["duration_ms"],
                trace=result["trace"],
            )
        except Exception as e:
            logger.debug("agent: sandbox save skipped: %s", e)


# ----------------------------------------------------------------------
# Default deterministic fast path (the existing brain pipeline)
# ----------------------------------------------------------------------

_engine = None


def _default_fast_path(query: str) -> dict | None:
    """Run the brain pipeline; return its API dict, or None when unhandled.

    The engine is created lazily (skill loading is expensive) and reused.
    Conversational hand-offs (NLP fallback) return the result too — the
    agent's success gating decides whether they short-circuit.
    """
    global _engine
    try:
        if _engine is None:
            from brain.engine import BrainEngine

            _engine = BrainEngine()
        return _engine.process(query).to_api_dict()
    except Exception as e:
        logger.warning("agent: brain pipeline unavailable: %s", e)
        return None


# ----------------------------------------------------------------------
# Module-level convenience
# ----------------------------------------------------------------------


def get_agent(config: Any = None) -> HermesAgent:
    """Build a HermesAgent from config (defaults when config is None)."""
    if config is None:
        config = ConfigLoader().load()
    return HermesAgent(
        max_iterations=getattr(config, "agent_max_iterations", DEFAULT_MAX_ITERATIONS),
        timeout_seconds=getattr(config, "agent_timeout", DEFAULT_AGENT_TIMEOUT),
    )
