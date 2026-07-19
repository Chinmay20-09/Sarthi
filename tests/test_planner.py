"""Tests for brain/planner.py.

Tests the pass-through planner and its contract.
Future multi-step tests will go here.
"""

import pytest

from brain.context import BrainContext
from brain.intent import Intent
from brain.planner import Planner


@pytest.fixture
def planner():
    return Planner()


@pytest.fixture
def context():
    return BrainContext(original_text="test command")


class TestPlanner:
    def test_returns_list(self, planner, context):
        """plan() should return a list."""
        intent = Intent(action="open", target="chrome")
        result = planner.plan(intent, context)
        assert isinstance(result, list)

    def test_returns_single_intent(self, planner, context):
        """Current implementation returns a single-element list."""
        intent = Intent(action="open", target="chrome")
        result = planner.plan(intent, context)
        assert len(result) == 1

    def test_preserves_intent(self, planner, context):
        """The returned intent should be the same object."""
        intent = Intent(action="open", target="chrome", confidence=0.95)
        result = planner.plan(intent, context)
        assert result[0] is intent
        assert result[0].action == "open"
        assert result[0].target == "chrome"
        assert result[0].confidence == 0.95

    def test_unknown_intent(self, planner, context):
        """Unknown actions should still be passed through."""
        intent = Intent(action="unknown", target="something", confidence=0.0)
        result = planner.plan(intent, context)
        assert len(result) == 1
        assert result[0].action == "unknown"

    def test_empty_intent(self, planner, context):
        """Empty intent should still be passed through."""
        intent = Intent()
        result = planner.plan(intent, context)
        assert len(result) == 1
        assert result[0].action == "unknown"

    def test_plan_does_not_mutate_context(self, planner, context):
        """Planner should not mutate the context object."""
        original_stage = context.stage
        planner.plan(Intent(action="test"), context)
        assert context.stage == original_stage
