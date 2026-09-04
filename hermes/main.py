from .config.loader import ConfigLoader
from .models import Task
from .orchestrator import HermesOrchestrator
from .providers.registry import build_provider_manager, is_local_only, resolve_provider_name
from .sandbox import TaskSandbox


def main() -> None:
    print("Hermes Agent initialized")

    print("Loading configuration...")
    config = ConfigLoader().load()

    provider_name = resolve_provider_name(config.provider)
    print(f"Selected provider: {provider_name}")

    print("Initializing Provider Manager...")
    manager = build_provider_manager(config)

    local_only = is_local_only(config)
    if local_only:
        # Explicit local mode: local provider only, no fallback
        test_task_id = "task_local_000001"
        test_prompt = "Reply with exactly: LOCAL_OLLAMA_PROVIDER_OK"
    else:
        # Remote mode: configured provider primary with local fallback
        print("Initializing Local Hermes as fallback...")
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
        if response.provider == "Ollama" and not local_only:
            print("Task completed using local fallback.")
        else:
            print("Task completed successfully.")
    else:
        print(f"Task failed: {response.error}")

    print("Hermes entering dormant state.")


if __name__ == "__main__":
    main()
