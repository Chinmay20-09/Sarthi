import time

from .agent import HermesAgent
from .models import ModelRequest, Task
from .providers.base import ProviderResponse
from .providers.manager import ProviderManager
from .sandbox import TaskSandbox
from .tool_registry import ToolRegistry


class HermesOrchestrator:
    """Hermes' provider wiring plus the two things the model can be asked for.

    There is exactly ONE model-driven reasoning loop in Sarthi — HermesAgent
    (``hermes/agent.py``), which owns retrieval, validated tool calls, the
    retry bound and sandbox persistence. The orchestrator does not implement a
    second loop; it only decides *what kind* of call the caller wants:

      1. ``chat(task)``    — plain conversation. NO tool planning, NO tool
         fetching, NO loop; the model is asked directly (the "natural language
         processor" path behind conversation mode and the NLP fallback skill).
      2. ``process(task)`` — a reasoning task. Delegates to HermesAgent, so
         tool validation, retrieval and persistence are identical to the
         /command complexity fallback.

    Provider selection and fallback (primary + local) stay here, because both
    paths must fail over the same way.
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        tool_registry: ToolRegistry | None = None,
        sandbox: TaskSandbox | None = None,
    ):
        self._provider_manager = provider_manager
        self._tool_registry = tool_registry
        self._sandbox = sandbox
        self._agent: HermesAgent | None = None

    @property
    def provider_manager(self) -> ProviderManager:
        """The provider manager backing this orchestrator (for diagnostics)."""
        return self._provider_manager

    def process(self, task: Task) -> ProviderResponse:
        """
        Run one reasoning task through the single Hermes loop, then report it
        as a ProviderResponse.

        HermesAgent retrieves bounded Sarthi context, lets the model answer or
        request one validated tool, repeats within the bounded iteration/time
        budget, and persists the run to the sandbox. The deterministic fast
        path is deliberately disabled here: every caller of ``process``
        (the /hermes/chat endpoint and the dev CLI) has already given Sarthi's
        pipeline the first chance.

        Args:
            task: The orchestration record (prompt, id, task_type, history,
                memory) to reason about.

        Returns:
            ProviderResponse from primary or fallback provider, with
            tool_used set when a registered Sarthi tool was executed.
        """
        result = self._get_agent().run(
            task.prompt,
            history=task.history,
            memory=task.memory,
            task_id=task.id,
            task_type=task.task_type,
        )
        return ProviderResponse(
            success=bool(result.get("success")),
            provider=result.get("provider") or "Hermes",
            model=result.get("model") or "",
            text=result.get("text") or "",
            tool_used=result.get("tool_used"),
            error=result.get("error"),
        )

    def _get_agent(self) -> HermesAgent:
        """The shared reasoning loop for this orchestrator (built once)."""
        if self._agent is None:
            from .config.loader import ConfigLoader

            config = ConfigLoader().load()
            self._agent = HermesAgent(
                generate=self._generate_with_fallback,
                tool_registry=self._tool_registry,
                sandbox=self._sandbox,
                fast_path=False,
                max_iterations=getattr(config, "agent_max_iterations", 3),
                timeout_seconds=getattr(config, "agent_timeout", 300.0),
            )
        return self._agent

    def chat(self, task: Task) -> ProviderResponse:
        """
        Plain conversational generation — NO tool planning, NO tool fetching.

        This is the "natural language processor" path: the model is asked
        directly for a conversational reply, never given the tool registry.
        The task is still saved to the sandbox (indexed by query) like every
        other Hermes execution, so the sandbox stays the single reference.

        Args:
            task: Task whose prompt is the user's message.

        Returns:
            ProviderResponse from primary or fallback provider.
        """
        trace: list[dict] = []

        started = time.perf_counter()
        response = self._generate_with_fallback(task)
        duration_ms = (time.perf_counter() - started) * 1000

        # Record the single chat step so the sandbox trace shows how the
        # reply was produced (provider + model, no tools involved).
        trace.append(
            {
                "step": "chat",
                "provider": response.provider,
                "model": response.model,
                "success": response.success,
                "text": response.text,
                "error": response.error,
            }
        )

        if self._sandbox is not None:
            self._sandbox.save(task, response, duration_ms, trace=trace)

        return response

    def _generate_with_fallback(self, task_or_request: Task | ModelRequest) -> ProviderResponse:
        """Call the primary provider, falling back to the fallback provider.

        Accepts the Task handed in by ``chat()`` or the ModelRequest built
        inside the agent loop; the ProviderManager normalizes either into a
        provider-neutral ModelRequest before any adapter sees it.
        """
        response = self._provider_manager.generate(task_or_request)

        # If primary succeeds, return immediately
        if response.success:
            return response

        # Primary failed, attempt fallback
        print(f"{response.provider} unavailable.")
        print("Preserving task...")
        print("Switching to fallback provider...")

        try:
            fallback_response = self._provider_manager.generate_fallback(task_or_request)
            return fallback_response
        except Exception:
            # Fallback failed completely (not initialized or errored)
            # Return a graceful combined failure response
            return ProviderResponse(
                success=False,
                provider="Hermes",
                model="",
                text="",
                error=f"{response.provider} failed ({response.error}) and fallback unavailable",
            )
