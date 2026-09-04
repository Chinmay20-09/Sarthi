"""Test fallback behavior from OpenRouter to Local Hermes."""

from hermes.config.settings import HermesConfig
from hermes.models import ModelRequest, Task
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
        self.last_request_received = None

    def generate(self, task: Task) -> ProviderResponse:
        """Record the received request and return success or failure."""
        self.last_request_received = task
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
    assert local.last_request_received is None, "Fallback should not be called"
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
    assert local.last_request_received is not None, "Fallback should be called"

    # The fallback receives the normalized provider-neutral request: the
    # prompt is preserved; orchestration metadata (id, task_type, context)
    # stays out of the provider boundary by design.
    assert isinstance(local.last_request_received, ModelRequest)
    assert local.last_request_received.prompt == "test prompt", "Prompt should be preserved"
    print("✅ PASS: Cloud failed, fallback succeeded, request preserved")


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
    """Test 4: Verify the request content is preserved through fallback."""
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

    # The provider boundary receives a normalized request: the prompt and
    # conversation fields survive the fallback; execution metadata (id,
    # task_type, context) intentionally does not cross into the adapter.
    received_request = local.last_request_received
    assert isinstance(received_request, ModelRequest)
    assert received_request.prompt == original_task.prompt, "Prompt not preserved"
    assert received_request.history is None
    assert received_request.memory is None
    print("✅ PASS: Request content preserved through fallback")


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
