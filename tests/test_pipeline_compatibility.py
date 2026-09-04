"""Focused compatibility tests for the pipeline's data boundaries.

These tests lock the SHAPES that flow between subsystems so a change on
one side can never silently break the next side:

    Scanner → Knowledge     scanner dicts (name/aliases/path/category)
                             are accepted by KnowledgeManager and come
                             back resolvable through get_all_entities.
    Knowledge → Resolver    entities built from scanner output resolve
                             to their canonical names.
    Brain → Hermes          the Natural Language Processor skill hands
                             the user's raw text to hermes.service.chat
                             and surfaces the reply with source="nlp".

Resolver → Executor is covered by test_brain_engine.py (BrainEngine DI);
Hermes → Tool Registry by test_tool_bridge.py. This file only adds the
boundaries above so the two don't overlap.
"""

from unittest.mock import patch

from brain.intent import Intent
from hermes.providers.base import ProviderResponse
from knowledge.entity_resolver import EntityResolver
from knowledge.manager import KnowledgeManager
from skills.scanner.application_scanner import Application

# ---------------------------------------------------------------------------
# Scanner → Knowledge → Resolver
# ---------------------------------------------------------------------------


def _scanner_shaped_apps() -> list[dict]:
    """Exactly what scan_all() returns: Application.to_dict() output."""
    return [
        Application(
            name="Google Chrome",
            path=__import__("pathlib").Path("C:/Program Files/Google/Chrome/chrome.exe"),
            aliases=["chrome", "google chrome"],
        ).to_dict(),
        Application(
            name="Steam",
            path=__import__("pathlib").Path("C:/Program Files (x86)/Steam/steam.exe"),
            aliases=["steam"],
            category="game",
        ).to_dict(),
        Application(
            name="Code",
            path=__import__("pathlib").Path("C:/Program Files/Microsoft VS Code/Code.exe"),
            aliases=["code", "vscode", "vs code", "visual studio code"],
        ).to_dict(),
    ]


def test_scanner_output_shape_is_accepted_by_knowledge_manager(tmp_path):
    """Scanner dicts must merge into the knowledge base untouched."""
    manager = KnowledgeManager(applications_path=tmp_path / "applications.json")

    result = manager.merge_scan_results(_scanner_shaped_apps())

    assert result["success"] is True
    assert len(result["new_unattended"]) == 3

    loaded = manager.load_applications()
    assert {app["name"] for app in loaded} == {"Google Chrome", "Steam", "Code"}
    # The game flag set by the scanner must survive the round trip.
    steam = next(a for a in loaded if a["name"] == "Steam")
    assert steam["category"] == "game"
    # The app_status stamp is added by the knowledge layer (not the scanner).
    for app in loaded:
        assert app["app_status"] == "unattended"
        assert set(app) >= {"name", "aliases", "path", "category", "app_status"}


def test_scanner_to_resolver_chain_resolves_entities(tmp_path):
    """Scanner output → KnowledgeManager → EntityResolver must resolve."""
    manager = KnowledgeManager(applications_path=tmp_path / "applications.json")
    manager.merge_scan_results(_scanner_shaped_apps())

    resolver = EntityResolver(entities=manager.get_all_entities())

    assert resolver.resolve("open vscode") == "open Code"
    assert resolver.resolve("launch chrome") == "launch Google Chrome"
    # The game is indexed with its canonical name.
    assert resolver.resolve("open steam") == "open Steam"


# ---------------------------------------------------------------------------
# Brain → Hermes (NLP fallback hands raw text to hermes.service.chat)
# ---------------------------------------------------------------------------


def test_nlp_skill_delegates_to_hermes_chat():
    """The conversational fallback must call hermes.service.chat with the
    user's raw text and surface the reply under source='nlp'."""
    from skills.natural_language_processor.main import NaturalLanguageProcessorSkill

    captured = {}

    def fake_chat(message, session_id=None):
        captured["message"] = message
        return ProviderResponse(
            success=True,
            provider="Ollama",
            model="hermes3:8b",
            text="Hello! I'm Sarthi's conversational layer.",
        )

    with patch("hermes.service.chat", side_effect=fake_chat):
        result = NaturalLanguageProcessorSkill().execute(
            Intent(action="unknown", raw_text="hello Sarthi", confidence=0.0)
        )

    assert result["success"] is True
    assert captured["message"] == "hello Sarthi"
    assert result["result"]["source"] == "nlp"
    assert "conversational layer" in result["result"]["message"]


def test_nlp_skill_claims_ownership_on_provider_failure():
    """When Hermes is unreachable the skill still owns the intent and
    returns a graceful handled error (no fallthrough to no_handler)."""
    from skills.natural_language_processor.main import NaturalLanguageProcessorSkill

    with patch(
        "hermes.service.chat",
        side_effect=RuntimeError("connection refused"),
    ):
        result = NaturalLanguageProcessorSkill().execute(
            Intent(action="how", raw_text="how are you", confidence=1.0)
        )

    assert result["success"] is False
    assert result["handled"] is True
    assert "language model" in result["error"]


def test_brain_engine_routes_conversation_to_nlp_skill():
    """engine.process() on conversational text must end at the NLP skill
    (the Brain → Hermes boundary through the executor fallback pool)."""
    from brain.engine import BrainEngine
    from brain.executor import BrainExecutor

    captured = {}

    def fake_chat(message, session_id=None):
        captured["message"] = message
        return ProviderResponse(
            success=True,
            provider="Ollama",
            model="hermes3:8b",
            text="I'm here to help.",
        )

    engine = BrainEngine(executor=BrainExecutor())
    with patch("hermes.service.chat", side_effect=fake_chat):
        response = engine.process("tell me a joke")

    assert response.success is True
    assert response.to_api_dict()["source"] == "nlp"
    assert "I'm here to help." in response.to_api_dict()["text"]
    # The NLP skill reconstructs the user message when raw_text is absent.
    assert captured["message"] == "tell me a joke"
