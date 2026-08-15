import time

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

    provider_name = (config.provider or "openrouter/free").lower()
    print(f"Selected provider: {provider_name}")
    if provider_name in ("local", "local_hermes", "localhermes"):
        print("Initializing Local Hermes...")
        manager.initialize(LocalHermesProvider(config))
    else:
        print("Initializing OpenRouter...")
        manager.initialize(OpenRouterProvider(config))

    orchestrator = HermesOrchestrator(manager)
    sandbox = TaskSandbox(config.sandbox_path)

    print("Creating task...")
    if provider_name in ("local", "local_hermes", "localhermes"):
        task = Task(
            id="task_local_000001",
            prompt="Reply with exactly: LOCAL_OLLAMA_PROVIDER_OK",
            task_type="test",
        )
    else:
        task = Task(
            id="task_000001",
            prompt="Introduce yourself as Hermes in one paragraph.",
            task_type="test",
        )

    print("Sending task...")
    print("Waiting for response...")
    started = time.perf_counter()
    response = orchestrator.process(task)
    duration_ms = (time.perf_counter() - started) * 1000

    print("Response received.")

    print("Saving task...")
    sandbox.save(task, response, duration_ms)

    if response.success:
        print("Task completed successfully.")
    else:
        print(f"Task failed: {response.error}")

    print("Hermes entering dormant state.")


if __name__ == "__main__":
    main()
