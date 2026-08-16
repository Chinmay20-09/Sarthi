from .config.loader import ConfigLoader
from .models import Task
from .orchestrator import HermesOrchestrator
from .providers.manager import ProviderManager
from .sandbox import TaskSandbox
from .providers.openrouter_provider import OpenRouterProvider
from .providers.local_provider import LocalHermesProvider


def main() -> None:
    print("Hermes Agent initialized")

    print("Loading configuration...")
    config = ConfigLoader().load()

    print("Initializing Provider Manager...")
    manager = ProviderManager()

    # Determine if user explicitly requested local-only mode
    provider_name = (config.provider or "openrouter/free").lower()
    explicit_local = provider_name in ("local", "local_hermes", "localhermes")

    if explicit_local:
        # Explicit local mode: use local provider only, no fallback
        print(f"Selected provider: {provider_name}")
        print("Initializing Local Hermes...")
        manager.initialize(LocalHermesProvider(config))
        test_task_id = "task_local_000001"
        test_prompt = "Reply with exactly: LOCAL_OLLAMA_PROVIDER_OK"
    else:
        # Default mode: OpenRouter primary with local fallback
        print(f"Selected provider: openrouter")
        print("Initializing OpenRouter...")
        manager.initialize(OpenRouterProvider(config))
        print("Initializing Local Hermes as fallback...")
        manager.set_fallback(LocalHermesProvider(config))
        test_task_id = "task_000001"
        test_prompt = "Introduce yourself as Hermes in one paragraph."

    # The orchestrator owns the sandbox: every task it processes is saved
    # to the sandbox, indexed by query, with its full execution trace.
    sandbox = TaskSandbox(config.sandbox_path)
    orchestrator = HermesOrchestrator(manager, sandbox=sandbox)

    print("Creating task...")
    task = Task(
        id=test_task_id,
        prompt=test_prompt,
        task_type="test",
    )

    print("Sending task...")
    print("Waiting for response...")
    response = orchestrator.process(task)

    if response.success:
        if response.provider == "Ollama" and not explicit_local:
            print("Task completed using local fallback.")
        else:
            print("Task completed successfully.")
    else:
        print(f"Task failed: {response.error}")

    print("Hermes entering dormant state.")


if __name__ == "__main__":
    main()
