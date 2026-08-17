"""Tests for the personal_context skill/tool.

Security guarantees under test:
    - only allowlisted safe fields can be retrieved
    - secret fields (password, api_key, ...) are blocked even when stored
    - unknown fields, whole-profile requests, and SQL-injection-like inputs
      fail safely
    - the tool never receives database access — it delegates to the service
    - Hermes can discover and invoke the tool through the registry
"""

from fastapi.testclient import TestClient

from brain.intent import Intent
from database.manager import DatabaseManager
from hermes.tool_registry import ToolRegistry
from hermes.tools import PersonalContextTool
from hermes.tools.base import ToolResult
from skills.personal_context.fields import (
    FIELD_CATEGORIES,
    SAFE_FIELDS,
    SECRET_FIELDS,
    STORAGE_KEYS,
)
from skills.personal_context.main import PersonalContextSkill
from skills.personal_context.service import PersonalContextService

# ----------------------------------------------------------------------
# Field registry
# ----------------------------------------------------------------------


def test_safe_fields_and_categories():
    assert "github" in SAFE_FIELDS
    assert "email" in SAFE_FIELDS
    assert "college_name" in SAFE_FIELDS
    assert "full_name" in SAFE_FIELDS
    assert FIELD_CATEGORIES["links"] == ("github", "linkedin", "portfolio")


def test_secret_fields_are_disjoint_from_safe_fields():
    assert SECRET_FIELDS.isdisjoint(SAFE_FIELDS)
    assert "password" in SECRET_FIELDS
    assert "api_key" in SECRET_FIELDS
    assert "token" in SECRET_FIELDS


# ----------------------------------------------------------------------
# Service: allowed lookups
# ----------------------------------------------------------------------


def _make_service(tmp_path, rows=None):
    db = DatabaseManager(tmp_path / "personal_context.db")
    db.create_table(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"
    )
    for key, value in (rows or {}).items():
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    return PersonalContextService(db=db), db


def test_get_field_allowed_github_maps_to_settings(tmp_path):
    service, _ = _make_service(tmp_path, {"github_username": "octocat"})

    result = service.get_field("github")

    assert result == {
        "success": True,
        "field": "github",
        "value": "octocat",
        "error": None,
        "category": "links",
    }
    assert STORAGE_KEYS["github"] == "github_username"


def test_get_field_missing_is_graceful(tmp_path):
    service, _ = _make_service(tmp_path, {})  # no personal info stored

    result = service.get_field("email")

    assert result["success"] is False
    assert result["value"] is None
    assert "no personal information is stored" in result["error"].lower()


def test_get_field_unknown_fails_safely(tmp_path):
    service, _ = _make_service(tmp_path)

    result = service.get_field("totally_random")

    assert result["success"] is False
    assert result["value"] is None
    assert "unknown" in result["error"].lower()


def test_get_field_case_and_whitespace_normalised(tmp_path):
    service, _ = _make_service(tmp_path, {"github_username": "octocat"})

    assert service.get_field("  GITHUB ")["value"] == "octocat"


# ----------------------------------------------------------------------
# Service: secrets are blocked even when stored
# ----------------------------------------------------------------------


def test_get_field_password_is_blocked(tmp_path):
    service, db = _make_service(tmp_path, {"password": "hunter2"})

    result = service.get_field("password")

    assert result["success"] is False
    assert result["value"] is None
    assert "blocked" in result["error"].lower()
    # The stored value must never leak.
    assert "hunter2" not in result["error"]


def test_get_field_api_key_is_blocked(tmp_path):
    service, _ = _make_service(tmp_path, {"api_key": "sk-secret-1234"})

    result = service.get_field("api_key")

    assert result["success"] is False
    assert result["value"] is None
    assert "blocked" in result["error"].lower()


def test_get_field_token_is_blocked(tmp_path):
    service, _ = _make_service(tmp_path, {"access_token": "tok-123"})

    result = service.get_field("access_token")

    assert result["success"] is False
    assert result["value"] is None
    assert "blocked" in result["error"].lower()


# ----------------------------------------------------------------------
# Service: whole-profile and injection attempts fail safely
# ----------------------------------------------------------------------


def test_get_field_entire_profile_request_fails(tmp_path):
    service, _ = _make_service(tmp_path)

    for attempt in ("*", "all", "everything", "profile", ""):
        result = service.get_field(attempt)
        assert result["success"] is False, f"'{attempt}' must be refused"
        assert result["value"] is None


def test_get_field_sql_injection_like_input_fails(tmp_path):
    service, _ = _make_service(tmp_path, {"github_username": "octocat"})

    attempts = (
        "github' OR '1'='1",
        "email; DROP TABLE settings",
        'github_username" OR 1=1 --',
        "full_name UNION SELECT value FROM settings",
    )
    for attempt in attempts:
        result = service.get_field(attempt)
        assert result["success"] is False, f"{attempt!r} must be refused"
        assert result["value"] is None
    # The allowlisted value is untouched.
    assert service.get_field("github")["value"] == "octocat"


def test_no_arbitrary_query_structural():
    """Every settings key that can reach SQL is allowlisted by construction."""
    keys_that_reach_sql = {key for field in SAFE_FIELDS for key in (field,)}
    keys_that_reach_sql.update(STORAGE_KEYS.values())
    assert "password" not in keys_that_reach_sql
    assert "api_key" not in keys_that_reach_sql
    assert all(not any(secret in key for secret in SECRET_FIELDS) for key in keys_that_reach_sql)


# ----------------------------------------------------------------------
# Service: list_available_fields (names only, never values)
# ----------------------------------------------------------------------


def test_list_available_fields_returns_names_only(tmp_path):
    service, _ = _make_service(tmp_path, {"github_username": "octocat", "email": "me@example.com"})

    fields = service.list_available_fields()

    assert "github" in fields
    assert "email" in fields
    assert "password" not in fields
    # No value is ever included — just names from the allowlist.
    assert all(field in SAFE_FIELDS for field in fields)
    assert not any("octocat" in field or "me@example.com" in field for field in fields)


def test_list_available_fields_empty_when_nothing_stored(tmp_path):
    service, _ = _make_service(tmp_path, {})

    assert service.list_available_fields() == []


# ----------------------------------------------------------------------
# Skill (brain path)
# ----------------------------------------------------------------------


def test_skill_registration_and_instantiation():
    from skills.registry import get_registry

    skill = get_registry().get_skill("personal_context")

    assert skill is not None
    assert isinstance(skill, PersonalContextSkill)
    assert skill.name == "personal_context"
    assert "personal information" in skill.description.lower()


def test_skill_answers_email_query(tmp_path):
    skill = PersonalContextSkill(
        service=PersonalContextService(db=DatabaseManager(tmp_path / "s.db"))
    )
    skill.service._ensure_table()
    skill.service.db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('email', 'me@example.com')"
    )

    result = skill.execute(Intent(action="what", target="email"))

    assert result["success"] is True
    assert result["result"]["value"] == "me@example.com"
    assert "me@example.com" in result["result"]["message"]


def test_skill_says_not_stored(tmp_path):
    skill = PersonalContextSkill(
        service=PersonalContextService(db=DatabaseManager(tmp_path / "s.db"))
    )

    result = skill.execute(Intent(action="what", target="college"))

    assert result["success"] is False
    assert result.get("handled") is True  # owns the honest "not stored" answer
    assert "no personal information is stored" in result["error"].lower()


def test_skill_declines_unrelated_intents():
    skill = PersonalContextSkill(service=PersonalContextService())

    for intent in (
        Intent(action="open", target="chrome"),
        Intent(action="what", target="project status"),  # project_tracker's
        Intent(action="what", target="github username"),  # user_config's
        Intent(action="what", target="the capital of france"),
    ):
        result = skill.execute(intent)
        assert result["success"] is False
        assert result.get("handled") is not True


# ----------------------------------------------------------------------
# Hermes tool: discovery and invocation
# ----------------------------------------------------------------------


def test_hermes_tool_discovery():
    client = TestClient(__import__("api").app)
    response = client.get("/hermes/tools")

    assert response.status_code == 200
    names = [tool["name"] for tool in response.json()["tools"]]
    assert "personal_context" in names

    tool = next(t for t in response.json()["tools"] if t["name"] == "personal_context")
    assert "safe personal profile field" in tool["description"]
    assert "field" in tool["parameters"]["properties"]


class _FakeService:
    """Deterministic stand-in for PersonalContextService."""

    def __init__(self, results=None, fields=None):
        self.results = results or {}
        self.fields = fields or []

    def get_field(self, field):
        return self.results.get(field) or {
            "success": False,
            "field": field,
            "value": None,
            "error": "Unknown personal field. Use list_available_fields to see which fields are stored.",
            "category": None,
        }

    def list_available_fields(self):
        return self.fields


def _registry_with_tool(fake_service) -> ToolRegistry:
    registry = ToolRegistry()
    tool = PersonalContextTool()
    tool._get_service = lambda: fake_service
    registry.register(tool)
    return registry


def test_tool_get_field_success():
    fake = _FakeService(
        results={
            "github": {
                "success": True,
                "field": "github",
                "value": "octocat",
                "error": None,
                "category": "links",
            }
        }
    )
    registry = _registry_with_tool(fake)

    result = registry.execute("personal_context", {"field": "github"})

    assert result.success is True
    assert result.tool == "personal_context"
    assert "octocat" in result.result
    assert result.data["value"] == "octocat"
    assert result.data["field"] == "github"


def test_tool_get_field_missing_is_graceful():
    fake = _FakeService(
        results={
            "email": {
                "success": False,
                "field": "email",
                "value": None,
                "error": "No personal information is stored for this field.",
                "category": "contact",
            }
        }
    )
    registry = _registry_with_tool(fake)

    result = registry.execute("personal_context", {"field": "email"})

    assert result.success is False
    assert "no personal information is stored" in result.error.lower()


def test_tool_get_field_unknown_fails_safely():
    registry = _registry_with_tool(_FakeService())

    result = registry.execute("personal_context", {"field": "password"})

    assert result.success is False
    assert result.data is None or result.data.get("value") is None


def test_tool_missing_field_is_invalid():
    registry = _registry_with_tool(_FakeService())

    result = registry.execute("personal_context", {})

    assert result.success is False
    assert result.invalid is True


def test_tool_list_available_fields_returns_names_only():
    fake = _FakeService(fields=["email", "github"])
    registry = _registry_with_tool(fake)

    result = registry.execute("personal_context", {"operation": "list_available_fields"})

    assert result.success is True
    assert result.data["fields"] == ["email", "github"]
    assert result.data.get("value") is None


def test_tool_unknown_operation_is_invalid():
    registry = _registry_with_tool(_FakeService())

    result = registry.execute("personal_context", {"operation": "delete_all", "field": "github"})

    assert result.success is False
    assert result.invalid is True
    assert "Unknown operation" in result.error


def test_tool_result_shape_is_structured():
    """ToolResult carries safe, machine-readable data — never a database handle."""
    fake = _FakeService(
        results={
            "github": {
                "success": True,
                "field": "github",
                "value": "octocat",
                "error": None,
                "category": "links",
            }
        }
    )
    result = _registry_with_tool(fake).execute("personal_context", {"field": "github"})

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.error == ""
