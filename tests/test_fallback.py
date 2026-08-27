"""Test fallback behavior from OpenRouter to Local Hermes."""

from hermes.config.settings import HermesConfig
from hermes.models import Task
from hermes.orchestrator import HermesOrchestrator
from hermes.providers.base import AIProvider, ProviderResponse
from hermes.providers.manager import ProviderManager


class MockOpenRouterProvider(AIProvider):
    """Mock OpenRouter provider for testing."""

    name = "MockOpenRouter"

    def __init__(self, config: HermesConfig, should_fail: bool = False):
        self._config = config
        self._should_fail = should_fail

    def generate(self, task: Task) -> ProviderResponse:
        """Return success or simulated failure."""
        if self._should_fail:
            return ProviderResponse(
                success=False,
                provider="OpenRouter",
                model=self._config.model,
                text="",
                error="Simulated cloud failure (API quota exceeded)",
            )
        return ProviderResponse(
            success=True,
            provider="OpenRouter",
            model=self._config.model,
            text="Mock response from OpenRouter",
        )


class MockLocalProvider(AIProvider):
    """Mock Local Hermes provider for testing."""

    name = "MockLocal"

    def __init__(self, config: HermesConfig, should_fail: bool = False):
        self._config = config
        self._should_fail = should_fail
        self.last_task_received = None

    def generate(self, task: Task) -> ProviderResponse:
        """Record task and return success or failure."""
        self.last_task_received = task
        if self._should_fail:
            return ProviderResponse(
                success=False,
                provider="Ollama",
                model=self._config.model,
                text="",
                error="Simulated local failure (Ollama unavailable)",
            )
        return ProviderResponse(
            success=True,
            provider="Ollama",
            model=self._config.model,
            text="Mock response from Local Hermes",
        )


def test_cloud_success():
    """Test 1: Cloud succeeds, fallback not called."""
    print("\n=== TEST 1: Cloud Success ===")
    config = HermesConfig(model="test-model")
    manager = ProviderManager()

    cloud = MockOpenRouterProvider(config, should_fail=False)
    local = MockLocalProvider(config, should_fail=False)

    manager.initialize(cloud)
    manager.set_fallback(local)

    orchestrator = HermesOrchestrator(manager)
    task = Task(id="test_001", prompt="test prompt", task_type="test")

    response = orchestrator.process(task)

    assert response.success is True, "Should succeed"
    assert response.provider == "OpenRouter", f"Should use OpenRouter, got {response.provider}"
    assert local.last_task_received is None, "Fallback should not be called"
    print("✅ PASS: Cloud success, no fallback invoked")


def test_cloud_failure_local_success():
    """Test 2: Cloud fails, fallback succeeds."""
    print("\n=== TEST 2: Cloud Failure → Local Success ===")
    config = HermesConfig(model="test-model")
    manager = ProviderManager()

    cloud = MockOpenRouterProvider(config, should_fail=True)
    local = MockLocalProvider(config, should_fail=False)

    manager.initialize(cloud)
    manager.set_fallback(local)

    orchestrator = HermesOrchestrator(manager)
    task = Task(id="test_002", prompt="test prompt", task_type="test", context={"key": "value"})

    response = orchestrator.process(task)

    assert response.success is True, "Should succeed via fallback"
    assert response.provider == "Ollama", f"Should use Ollama, got {response.provider}"
    assert local.last_task_received is not None, "Fallback should be called"

    # Verify task preservation
    assert local.last_task_received.id == "test_002", "Task ID should be preserved"
    assert local.last_task_received.prompt == "test prompt", "Prompt should be preserved"
    assert local.last_task_received.task_type == "test", "Task type should be preserved"
    assert local.last_task_received.context == {"key": "value"}, "Context should be preserved"
    print("✅ PASS: Cloud failed, fallback succeeded, task preserved")


def test_both_providers_fail():
    """Test 3: Both cloud and local fail."""
    print("\n=== TEST 3: Both Providers Fail ===")
    config = HermesConfig(model="test-model")
    manager = ProviderManager()

    cloud = MockOpenRouterProvider(config, should_fail=True)
    local = MockLocalProvider(config, should_fail=True)

    manager.initialize(cloud)
    manager.set_fallback(local)

    orchestrator = HermesOrchestrator(manager)
    task = Task(id="test_003", prompt="test prompt", task_type="test")

    response = orchestrator.process(task)

    assert response.success is False, "Should fail when both fail"
    assert response.provider == "Ollama", (
        f"Last attempted provider should be Ollama, got {response.provider}"
    )
    print("✅ PASS: Both providers failed gracefully")


def test_task_preservation():
    """Test 4: Verify task preservation through fallback."""
    print("\n=== TEST 4: Task Preservation ===")
    config = HermesConfig(model="test-model")
    manager = ProviderManager()

    cloud = MockOpenRouterProvider(config, should_fail=True)
    local = MockLocalProvider(config, should_fail=False)

    manager.initialize(cloud)
    manager.set_fallback(local)

    orchestrator = HermesOrchestrator(manager)

    # Create a task with all fields populated
    original_task = Task(
        id="test_004",
        prompt="Complex prompt with special characters: !@#$%^&*()",
        task_type="complex",
        context={
            "nested": {"data": [1, 2, 3]},
            "metadata": "test",
        },
    )

    response = orchestrator.process(original_task)

    assert response.success is True, "Should succeed via fallback"

    # Verify all task fields are preserved
    received_task = local.last_task_received
    assert received_task.id == original_task.id, "ID not preserved"
    assert received_task.prompt == original_task.prompt, "Prompt not preserved"
    assert received_task.task_type == original_task.task_type, "Type not preserved"
    assert received_task.context == original_task.context, "Context not preserved"
    print("✅ PASS: All task fields preserved through fallback")


def test_no_fallback_in_local_only_mode():
    """Test 5: Explicit local mode should not try cloud first."""
    print("\n=== TEST 5: Local-Only Mode ===")
    config = HermesConfig(model="test-model")
    manager = ProviderManager()

    local = MockLocalProvider(config, should_fail=False)

    manager.initialize(local)  # Initialize with local only
    # Note: no fallback set

    orchestrator = HermesOrchestrator(manager)
    task = Task(id="test_005", prompt="test prompt", task_type="test")

    response = orchestrator.process(task)

    assert response.success is True, "Should succeed with local"
    assert response.provider == "Ollama", "Should use local provider"
    print("✅ PASS: Local-only mode works without fallback")


if __name__ == "__main__":
    test_cloud_success()
    test_cloud_failure_local_success()
    test_both_providers_fail()
    test_task_preservation()
    test_no_fallback_in_local_only_mode()
    print("\n=== ALL TESTS PASSED ===\n")
