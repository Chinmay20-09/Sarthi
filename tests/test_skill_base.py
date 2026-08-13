"""Tests for skills/base.py.

Tests the BaseSkill abstract base class contract.
Every skill must inherit from BaseSkill and implement execute(intent).
"""

from typing import Any

import pytest

from brain.intent import Intent
from skills.base import BaseSkill


class TestBaseSkillInstantiation:
    """BaseSkill cannot be instantiated directly (it's abstract)."""

    def test_cannot_instantiate_abstract(self):
        """Direct instantiation should raise TypeError."""
        with pytest.raises(TypeError):
            BaseSkill()  # type: ignore


class TestConcreteSkill:
    """A proper skill implementation must work."""

    def test_concrete_skill_works(self):
        """A skill implementing execute() should work."""

        class MySkill(BaseSkill):
            name = "my_skill"
            description = "A test skill"
            version = "1.0.0"

            def execute(self, intent: Intent) -> dict[str, Any]:
                return {"success": True, "result": intent.action}

        skill = MySkill()
        result = skill.execute(Intent(action="test"))
        assert result["success"] is True
        assert result["result"] == "test"

    def test_default_attributes(self):
        """Skill should have sensible defaults for name/description/version."""

        class MinimalSkill(BaseSkill):
            def execute(self, intent: Intent) -> dict[str, Any]:
                return {"success": True}

        skill = MinimalSkill()
        assert skill.name == "unnamed_skill"
        assert skill.description == ""
        assert skill.version == "0.1.0"

    def test_custom_attributes(self):
        """Skill should respect custom name/description/version."""

        class CustomSkill(BaseSkill):
            name = "custom"
            description = "Custom skill"
            version = "2.0.0"

            def execute(self, intent: Intent) -> dict[str, Any]:
                return {"success": True}

        skill = CustomSkill()
        assert skill.name == "custom"
        assert skill.description == "Custom skill"
        assert skill.version == "2.0.0"


class TestSkillWithoutExecute:
    """A class inheriting BaseSkill without implementing execute()."""

    def test_missing_execute_raises_typeerror(self):
        """Cannot instantiate a skill that doesn't implement execute()."""
        with pytest.raises(TypeError):

            class IncompleteSkill(BaseSkill):
                pass

            IncompleteSkill()  # type: ignore


class TestExecuteContract:
    """The execute() method must return a dict with expected fields."""

    def test_execute_returns_dict(self):
        """execute() should return a dictionary."""

        class TestSkill(BaseSkill):
            name = "test"

            def execute(self, intent: Intent) -> dict[str, Any]:
                return {"success": True, "status": "done", "result": "ok"}

        skill = TestSkill()
        result = skill.execute(Intent(action="test"))
        assert isinstance(result, dict)
        assert "success" in result

    def test_execute_error_response(self):
        """execute() should support error responses."""

        class TestSkill(BaseSkill):
            name = "test"

            def execute(self, intent: Intent) -> dict[str, Any]:
                return {"success": False, "status": "error", "error": "Something went wrong"}

        skill = TestSkill()
        result = skill.execute(Intent(action="unknown"))
        assert result["success"] is False
        assert "error" in result

    def test_execute_accepts_intent(self):
        """execute() must accept an Intent object."""

        class TestSkill(BaseSkill):
            name = "test"

            def execute(self, intent: Intent) -> dict[str, Any]:
                return {
                    "success": True,
                    "action": intent.action,
                    "target": intent.target,
                }

        skill = TestSkill()
        result = skill.execute(Intent(action="open", target="chrome"))
        assert result["action"] == "open"
        assert result["target"] == "chrome"


class TestRepr:
    """__repr__ should be human-readable."""

    def test_repr_includes_class_name(self):
        class TestSkill(BaseSkill):
            name = "test"

            def execute(self, intent: Intent) -> dict[str, Any]:
                return {"success": True}

        skill = TestSkill()
        assert "TestSkill" in repr(skill)
        assert "test" in repr(skill)
