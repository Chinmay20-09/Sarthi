"""Integration test for cloud failure → local fallback."""

import sys
import time
from pathlib import Path

# Add hermes to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hermes.config.settings import HermesConfig
from hermes.models import Task
from hermes.orchestrator import HermesOrchestrator
from hermes.providers.base import ProviderResponse, AIProvider
from hermes.providers.manager import ProviderManager
from hermes.sandbox import TaskSandbox


class FailingCloudProvider(AIProvider):
    """Simulated OpenRouter that fails."""

    name = "OpenRouter"

    def __init__(self, config: HermesConfig):
        self._config = config

    def generate(self, task: Task) -> ProviderResponse:
        """Simulate cloud failure."""
        return ProviderResponse(
            success=False,
            provider=self.name,
            model=self._config.model,
            text="",
            error="Simulated cloud error: API rate limit exceeded",
        )


class SuccessfulLocalProvider(AIProvider):
    """Simulated Ollama that succeeds."""

    name = "Ollama"

    def __init__(self, config: HermesConfig):
        self._config = config

    def generate(self, task: Task) -> ProviderResponse:
        """Simulate successful local response."""
        return ProviderResponse(
            success=True,
            provider=self.name,
            model=self._config.model,
            text=f"Local response to: {task.prompt}",
        )


def test_fallback_integration():
    """Integration test: Cloud fails -> Local succeeds."""
    print("\n=== INTEGRATION TEST: Cloud Failure to Local Fallback ===\n")
    
    config = HermesConfig(
        model="hermes3:8b",
        sandbox_path="sandbox_test",
    )

    # Setup providers
    manager = ProviderManager()
    cloud = FailingCloudProvider(config)
    local = SuccessfulLocalProvider(config)

    manager.initialize(cloud)
    manager.set_fallback(local)

    # Create orchestrator and sandbox
    orchestrator = HermesOrchestrator(manager)
    sandbox = TaskSandbox(config.sandbox_path)

    # Create and process task
    task = Task(
        id="fallback_test_001",
        prompt="This task will trigger fallback",
        task_type="integration_test",
        context={"test": "data"},
    )

    print(f"Creating task: {task.id}")
    print(f"Prompt: {task.prompt}")
    print("\nAttempting cloud provider...")
    print("Waiting for response...")

    start = time.perf_counter()
    response = orchestrator.process(task)
    duration_ms = (time.perf_counter() - start) * 1000

    print(f"\nResponse received.")
    print(f"Provider: {response.provider}")
    print(f"Model: {response.model}")
    print(f"Success: {response.success}")
    print(f"Duration: {duration_ms:.2f}ms")

    # Verify expectations
    assert response.success is True, "Should succeed via fallback"
    assert response.provider == "Ollama", f"Should use Ollama, got {response.provider}"
    assert response.model == "hermes3:8b", f"Should use hermes3:8b, got {response.model}"

    # Save to sandbox
    print("\nSaving to sandbox...")
    sandbox.save(task, response, duration_ms)

    # Verify sandbox files
    task_dir = Path(config.sandbox_path) / "tasks" / task.id
    assert (task_dir / "prompt.md").exists(), "prompt.md not created"
    assert (task_dir / "response.md").exists(), "response.md not created"
    assert (task_dir / "metadata.json").exists(), "metadata.json not created"

    # Verify content
    prompt_content = (task_dir / "prompt.md").read_text()
    assert prompt_content == task.prompt, "Prompt not preserved"

    response_content = (task_dir / "response.md").read_text()
    assert len(response_content) > 0, "Response empty"

    metadata_json = (task_dir / "metadata.json").read_text()
    assert "Ollama" in metadata_json, "Ollama not in metadata"
    assert "success" in metadata_json, "Status not in metadata"

    print(f"[PASS] Sandbox verification passed")
    print(f"[PASS] All assertions passed")
    print("\n=== INTEGRATION TEST PASSED ===\n")


if __name__ == "__main__":
    test_fallback_integration()
