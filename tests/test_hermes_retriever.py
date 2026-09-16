"""Tests for the Hermes hybrid retriever (Backend/hermes/retriever.py).

Phase 3b contract:
- Bounded retrieval over existing stores: knowledge_memory, command_history,
  settings, knowledge entities, sandbox index, conversation history.
- The existing Sarthi .db stays the source of truth (no new database).
- Every section is capped; the total is capped by MAX_TOTAL_CHARS.
- Every store failure degrades to fewer sources — retrieve() never raises.
- Secret-looking settings keys never reach a prompt.
"""

from pathlib import Path

import pytest
from database.manager import DatabaseManager
from hermes.retriever import (
    MAX_HISTORY_CHARS,
    MAX_TOTAL_CHARS,
    Context,
    Retriever,
    _assemble,
    _clip,
    _is_secret_key,
    _keywords,
    _retrieve_memory,
    _retrieve_settings,
    _secret_fields,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> DatabaseManager:
    """A real DatabaseManager on a tmp file — canonical schema self-heals."""
    return DatabaseManager(tmp_path / "retriever_test.db")


@pytest.fixture()
def sandbox(tmp_path: Path):
    from hermes.sandbox import TaskSandbox

    return TaskSandbox(tmp_path / "sandbox")


def _add_memory(db: DatabaseManager, key: str, value: str) -> None:
    db.execute(
        "INSERT OR REPLACE INTO knowledge_memory (key, value, updated_at) "
        "VALUES (?, ?, datetime('now'))",
        (key, value),
    )


def _add_history(
    db: DatabaseManager, command: str, action: str, target: str, success: int = 1
) -> None:
    db.execute(
        "INSERT INTO command_history (command, action, target, success, timestamp) "
        "VALUES (?, ?, ?, ?, datetime('now'))",
        (command, action, target, success),
    )


def _add_setting(db: DatabaseManager, key: str, value: str) -> None:
    db.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        (key, value),
    )


# ---------------------------------------------------------------------------
# Helpers: keywords, clipping, assembly
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_keywords_drops_stopwords_and_dedupes(self):
        words = _keywords("How do I fix the backend latency in the backend")
        assert "backend" in words
        assert "latency" in words
        assert "the" not in words
        assert "how" not in words
        assert len(words) == len(set(words))

    def test_keywords_longest_first(self):
        words = _keywords("fix latency in the api")
        assert words[0] in ("latency", "fix")  # 8/3 chars — longest first

    def test_keywords_empty_query(self):
        assert _keywords("") == []
        assert _keywords("the a an and") == []

    def test_clip_short_text_unchanged(self):
        assert _clip("hello", 10) == "hello"

    def test_clip_long_text_truncates_with_ellipsis(self):
        out = _clip("x" * 100, 10)
        assert len(out) == 10
        assert out.endswith("\u2026")

    def test_assemble_respects_budget(self):
        sections = [f"section {i}: {'a' * 500}" for i in range(20)]
        text = _assemble(sections, MAX_TOTAL_CHARS)
        assert len(text) <= MAX_TOTAL_CHARS

    def test_assemble_keeps_earlier_sections(self):
        text = _assemble(["first", "second", "third"], 20)
        assert text.startswith("first")


# ---------------------------------------------------------------------------
# Memory retrieval (knowledge_memory)
# ---------------------------------------------------------------------------


class TestMemoryRetrieval:
    def test_matching_fact_retrieved(self, db):
        _add_memory(db, "user_project", "Sarthi is a desktop assistant")
        facts, sources = _retrieve_memory(db, ["sarthi"])

        assert sources[0].name == "memory"
        assert sources[0].count == len(facts)
        assert facts and "Sarthi" in facts[0]

    def test_fallback_to_recent_when_no_match(self, db):
        _add_memory(db, "pref_theme", "dark mode")
        facts, sources = _retrieve_memory(db, ["zzz_nonexistent"])

        assert sources[0].count == len(facts)  # still returns recent rows
        assert facts

    def test_empty_table_returns_no_facts(self, db):
        facts, sources = _retrieve_memory(db, ["anything"])
        assert facts == []
        assert sources[0].count == 0

    def test_broken_db_degrades_not_raises(self):
        facts, sources = _retrieve_memory(None, ["x"])
        assert facts == []
        assert sources[0].name == "memory"

    def test_facts_are_capped(self, db):
        for i in range(30):
            _add_memory(db, f"fact_{i}_latency", f"value {i}")
        facts, _ = _retrieve_memory(db, ["latency"])
        assert len(facts) <= 12  # MAX_MEMORY_FACTS


# ---------------------------------------------------------------------------
# History retrieval (command_history)
# ---------------------------------------------------------------------------


class TestHistoryRetrieval:
    def test_matching_commands_retrieved(self, db):
        _add_history(db, "open youtube", "open", "youtube")
        _add_history(db, "close chrome", "close", "chrome")
        result, sources = _retrieve_history_result(db, ["youtube"])

        text = result[0] if result else ""
        assert sources[0].name == "command_history"
        assert "youtube" in text.lower()
        assert "chrome" not in text.lower()

    def test_lines_are_capped(self, db):
        for i in range(20):
            _add_history(db, f"run report {i}", "open", f"target{i}")
        result, _ = _retrieve_history_result(db, ["report"])
        text = result[0] if result else ""
        assert len(text) <= MAX_HISTORY_CHARS

    def test_broken_db_degrades_not_raises(self):
        result, sources = _retrieve_history_result(None, ["x"])
        assert result == []
        assert sources[0].name == "command_history"


def _retrieve_history_result(db, keywords):
    from hermes.retriever import _retrieve_history

    return _retrieve_history(db, keywords)


# ---------------------------------------------------------------------------
# Settings retrieval + secret masking
# ---------------------------------------------------------------------------


class TestSettingsRetrieval:
    def test_normal_settings_returned(self, db):
        _add_setting(db, "github_username", "octocat")
        lines, sources = _retrieve_settings(db)

        assert any("github_username: octocat" in line for line in lines)
        assert sources[0].name == "settings"

    def test_secret_keys_are_withheld(self, db):
        _add_setting(db, "github_username", "octocat")
        _add_setting(db, "api_key", "sk-live-999")
        _add_setting(db, "access_token", "tok-123")
        lines, sources = _retrieve_settings(db)

        joined = "\n".join(lines)
        assert "sk-live-999" not in joined
        assert "tok-123" not in joined
        assert "api_key" not in joined
        assert "access_token" not in joined
        assert "github_username: octocat" in joined
        assert sources[0].detail["withheld"] == 2

    def test_secret_fields_imported_from_personal_context(self):
        fields = _secret_fields()
        assert "password" in fields
        assert "api_key" in fields
        assert "token" in fields

    def test_is_secret_key_detection(self):
        assert _is_secret_key("api_key")
        assert _is_secret_key("MY_PASSWORD")
        assert _is_secret_key("access_token")
        assert _is_secret_key("openai_secret")
        assert not _is_secret_key("github_username")
        assert not _is_secret_key("theme")

    def test_values_are_clipped(self, db):
        _add_setting(db, "long_value", "y" * 500)
        lines, _ = _retrieve_settings(db)
        assert all(len(line) <= 80 for line in lines)


# ---------------------------------------------------------------------------
# Full retrieve() over the real database layer
# ---------------------------------------------------------------------------


class TestRetrieveIntegration:
    def test_retrieve_returns_context_with_sources(self, db, sandbox):
        _add_memory(db, "latency_note", "Hermes p95 latency is 900ms")
        _add_history(db, "open chatgpt", "open", "chatgpt")
        retriever = Retriever(sandbox=sandbox, db=db)

        context = retriever.retrieve("fix the hermes latency problem", session_id=None)

        assert isinstance(context, Context)
        assert context.text  # non-empty bounded context
        assert context.total_chars == len(context.text)
        assert context.total_chars <= MAX_TOTAL_CHARS
        names = {s.name for s in context.sources}
        assert "memory" in names
        assert "command_history" in names
        assert context.duration_ms > 0

    def test_retrieve_is_bounded(self, db, sandbox):
        for i in range(50):
            _add_memory(db, f"note_{i}_latency", "x" * 200)
        retriever = Retriever(sandbox=sandbox, db=db)

        context = retriever.retrieve("latency notes everywhere")

        assert context.total_chars <= MAX_TOTAL_CHARS

    def test_retrieve_with_session_history(self, db, sandbox):
        from hermes.conversation import ConversationStore

        store = ConversationStore(db=db)
        store.add_turn("s1", "user", "what is the latency")
        store.add_turn("s1", "assistant", "p95 was 900ms")
        retriever = Retriever(sandbox=sandbox, db=db, conversation_store=store)

        context = retriever.retrieve("summarize the latency", session_id="s1")

        names = {s.name for s in context.sources}
        assert "conversation" in names
        assert "latency" in context.text.lower()

    def test_retrieve_without_session_is_graceful(self, db, sandbox):
        retriever = Retriever(sandbox=sandbox, db=db)
        context = retriever.retrieve("anything", session_id=None)
        names = {s.name for s in context.sources}
        assert "conversation" in names
        assert all(s.count == 0 for s in context.sources if s.name == "conversation")

    def test_retrieve_empty_query_still_returns_sources(self, db, sandbox):
        retriever = Retriever(sandbox=sandbox, db=db)
        context = retriever.retrieve("")
        assert isinstance(context, Context)
        assert context.sources  # every store reported (possibly zero rows)


# ---------------------------------------------------------------------------
# Sandbox retrieval (past Hermes tasks)
# ---------------------------------------------------------------------------


class TestSandboxRetrieval:
    def test_past_task_matched_by_keywords(self, db, sandbox):
        from hermes.models import Task
        from hermes.providers.base import ProviderResponse

        task = Task(prompt="fix the sarthi backend latency")
        response = ProviderResponse(
            success=True, provider="Ollama", model="hermes3:8b", text="done"
        )
        sandbox.save(task, response, duration_ms=123.0)

        retriever = Retriever(sandbox=sandbox)
        context = retriever.retrieve("what did we do about the sarthi latency")

        names = {s.name for s in context.sources}
        assert "sandbox" in names
        sandbox_source = next(s for s in context.sources if s.name == "sandbox")
        assert sandbox_source.count >= 1

    def test_no_match_returns_zero_count(self, db, sandbox):
        retriever = Retriever(sandbox=sandbox)
        context = retriever.retrieve("zzz unique query words here")
        sandbox_source = next(s for s in context.sources if s.name == "sandbox")
        assert sandbox_source.count == 0

    def test_retriever_without_sandbox_is_graceful(self, db):
        retriever = Retriever(sandbox=None, db=db)
        context = retriever.retrieve("fix the latency")
        sandbox_source = next(s for s in context.sources if s.name == "sandbox")
        assert sandbox_source.count == 0


# ---------------------------------------------------------------------------
# Knowledge entity retrieval (apps + websites)
# ---------------------------------------------------------------------------


class TestKnowledgeRetrieval:
    def test_websites_retrieved_by_name(self, db, sandbox):
        retriever = Retriever(sandbox=sandbox)
        context = retriever.retrieve("open youtube")

        # youtube.com is in the shipped knowledge base
        names = {s.name for s in context.sources}
        assert "knowledge" in names
        knowledge_source = next(s for s in context.sources if s.name == "knowledge")
        assert knowledge_source.count >= 1

    def test_context_as_dict_shape(self, db, sandbox):
        retriever = Retriever(sandbox=sandbox)
        context = retriever.retrieve("open youtube")
        d = context.as_dict()

        assert {"duration_ms", "total_chars", "sources"} <= set(d)
        assert all({"name", "kind", "count", "duration_ms"} <= set(s) for s in d["sources"])


# ---------------------------------------------------------------------------
# The 8B-model / embedding ban
# ---------------------------------------------------------------------------


class TestRetrieverIsLightweight:
    def test_retriever_module_never_imports_heavy_stacks(self):
        import subprocess
        import sys

        code = (
            "import sys; import hermes.retriever;"
            "assert 'hermes.orchestrator' not in sys.modules;"
            "assert 'hermes.providers' not in sys.modules;"
            "assert 'hermes.agent' not in sys.modules;"
            "assert 'sentence_transformers' not in sys.modules;"
            "assert 'torch' not in sys.modules;"
            "print('clean')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
        )
        assert result.returncode == 0, result.stderr
        assert "clean" in result.stdout

    def test_retrieve_is_fast(self, db, sandbox):
        import time

        _add_memory(db, "latency", "p95 900ms")
        retriever = Retriever(sandbox=sandbox, db=db)

        start = time.perf_counter()
        for _ in range(20):
            retriever.retrieve("fix the hermes latency problem")
        elapsed = time.perf_counter() - start

        # 20 retrievals over a real (tiny) DB must stay well under 2s.
        assert elapsed < 2.0, f"retrieval too slow: {elapsed:.2f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
