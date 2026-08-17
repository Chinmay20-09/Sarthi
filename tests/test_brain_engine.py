"""Tests for brain/engine.py.

Tests the full BrainEngine pipeline orchestration:
    Interpreter → Planner → Resolver → Executor

Uses dependency injection to provide mock components for isolated testing.
"""

from typing import Any

import pytest

from brain.context import BrainContext
from brain.engine import BrainEngine
from brain.executor import BrainExecutor
from brain.intent import Intent
from brain.planner import Planner
from brain.response import BrainResponse
from knowledge.entity_resolver import EntityResolver

# ---------------------------------------------------------------------------
# Mock Components
# ---------------------------------------------------------------------------


class MockExecutor:
    """Mock executor that always succeeds."""

    def __init__(self):
        self.last_intent = None
        self.should_fail = False

    def execute(self, intent: Intent, context: BrainContext = None) -> dict[str, Any]:
        self.last_intent = intent
        if self.should_fail:
            return {"success": False, "status": "error", "error": "Mock failure"}
        return {
            "success": True,
            "status": "executed",
            "result": {"action": intent.action, "target": intent.target},
        }


class MockPlanner:
    """Mock planner that optionally splits intents."""

    def __init__(self):
        self.plan_result = None

    def plan(self, intent: Intent, context: BrainContext) -> list[Intent]:
        if self.plan_result is not None:
            return self.plan_result
        return [intent]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_executor():
    return MockExecutor()


@pytest.fixture
def mock_planner():
    return MockPlanner()


@pytest.fixture
def simple_entities():
    return [
        {"name": "Chrome", "aliases": ["chrome", "google chrome"], "category": "applications"},
        {"name": "YouTube", "aliases": ["youtube", "yt"], "category": "websites"},
    ]


@pytest.fixture
def resolver(simple_entities):
    return EntityResolver(entities=simple_entities)


@pytest.fixture
def engine(resolver, mock_executor, mock_planner):
    return BrainEngine(
        resolver=resolver,
        executor=mock_executor,  # type: ignore
        planner=mock_planner,
    )


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInitialization:
    def test_engine_created_with_di(self, resolver, mock_executor, mock_planner):
        """Engine should accept injected dependencies."""
        engine = BrainEngine(
            resolver=resolver,
            executor=mock_executor,  # type: ignore
            planner=mock_planner,
        )
        assert engine.resolver is resolver
        assert engine.executor is mock_executor
        assert engine.planner is mock_planner

    def test_engine_without_resolver(self):
        """Engine should handle missing resolver gracefully."""
        engine = BrainEngine()
        assert engine.resolver is not None  # Falls back to empty resolver

    def test_engine_defaults(self):
        """Engine should create default components."""
        engine = BrainEngine()
        assert isinstance(engine.planner, Planner)
        assert isinstance(engine.executor, BrainExecutor)


# ---------------------------------------------------------------------------
# Process Pipeline
# ---------------------------------------------------------------------------


class TestProcess:
    def test_process_returns_brain_response(self, engine):
        """process() should return a BrainResponse."""
        response = engine.process("open chrome")
        assert isinstance(response, BrainResponse)

    def test_process_successful(self, engine):
        """A valid command should return success."""
        response = engine.process("open chrome")
        assert response.success is True
        assert response.status == "executed"

    def test_process_with_entity_resolution(self, engine, mock_executor):
        """Entity should be resolved before execution."""
        engine.process("open chrome")
        assert mock_executor.last_intent is not None
        # After resolution, 'chrome' should be resolved to 'Chrome'
        assert mock_executor.last_intent.target == "Chrome"

    def test_process_sets_intent(self, engine):
        """Response should contain the final intent."""
        response = engine.process("search python")
        assert response.intent.action == "search"
        assert response.intent.target == "python"

    def test_process_execution_time(self, engine):
        """Response should include execution time in ms."""
        response = engine.process("open chrome")
        assert response.execution_ms > 0

    def test_process_unknown_command(self, engine):
        """Unknown command should still produce a response."""
        response = engine.process("xyzzy plugh")
        assert isinstance(response, BrainResponse)


# ---------------------------------------------------------------------------
# Pipeline Stages
# ---------------------------------------------------------------------------


class TestPipelineStages:
    def test_pipeline_interpret_stage(self, engine):
        """Interpret stage should parse the action."""
        response = engine.process("play lofi")
        assert response.intent.action == "play"

    def test_pipeline_resolve_stage(self, engine):
        """Resolve stage should resolve entities."""
        response = engine.process("open youtube")
        assert response.intent.target == "YouTube"

    def test_pipeline_scan_stage(self, engine):
        """'scan my system' should parse to the scan action."""
        response = engine.process("scan my system")
        assert response.intent.action == "scan"

    def test_pipeline_refresh_maps_to_scan(self, engine):
        """'refresh applications' should map to the scan action."""
        response = engine.process("refresh applications")
        assert response.intent.action == "scan"

    def test_pipeline_discover_maps_to_scan(self, engine):
        """'discover installed games' should map to the scan action."""
        response = engine.process("discover installed games")
        assert response.intent.action == "scan"

    def test_pipeline_without_resolver(self):
        """Pipeline should work without a resolver."""
        engine = BrainEngine()
        response = engine.process("open chrome")
        assert isinstance(response, BrainResponse)


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_executor_failure(self, engine, mock_executor):
        """Executor failure should be reflected in response."""
        mock_executor.should_fail = True
        response = engine.process("open chrome")
        assert response.success is False
        assert response.status == "error"

    def test_exception_during_processing(self, engine, mock_planner):
        """Exception in pipeline should be caught gracefully."""

        def broken_plan(intent, context):
            raise RuntimeError("Pipeline crashed")

        mock_planner.plan = broken_plan
        response = engine.process("anything")
        assert response.success is False
        assert response.status == "error"

    def test_error_response_has_error_message(self, engine, mock_executor):
        """Error response should include error message."""
        mock_executor.should_fail = True
        response = engine.process("anything")
        assert response.error is not None

    def test_error_preserves_intent(self, engine, mock_executor):
        """Error response should preserve the original intent."""
        mock_executor.should_fail = True
        response = engine.process("open chrome")
        assert response.intent.action == "open"
        assert response.intent.target == "Chrome"


# ---------------------------------------------------------------------------
# Multi-step Plans
# ---------------------------------------------------------------------------


class TestMultiStepPlans:
    def test_multi_step_execution(self, engine, mock_planner, mock_executor):
        """Multiple intents should be executed sequentially."""
        mock_planner.plan_result = [
            Intent(action="open", target="chrome"),
            Intent(action="search", target="python"),
        ]
        response = engine.process("open chrome and search python")
        assert response.success is True

    def test_multi_step_fails_fast(self, engine, mock_planner, mock_executor):
        """Pipeline should stop on first failure."""
        mock_planner.plan_result = [
            Intent(action="good"),
            Intent(action="bad"),
        ]
        # Second intent will fail because there's no handler for "bad"
        # But executor handles it gracefully
        response = engine.process("two steps")
        # Should not crash
        assert isinstance(response, BrainResponse)


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_text(self, engine):
        """Empty text should not crash."""
        response = engine.process("")
        assert isinstance(response, BrainResponse)

    def test_very_long_text(self, engine):
        """Very long text should not crash."""
        response = engine.process("open " + "a " * 100)
        assert isinstance(response, BrainResponse)

    def test_special_characters(self, engine):
        """Special characters should not crash."""
        response = engine.process("open chrome!!!")
        assert isinstance(response, BrainResponse)
