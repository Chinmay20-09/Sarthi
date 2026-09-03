"""Tests for brain/wordfinder.py — keyword-DB target detection.

The wordfinder stops an \"open ...\" target at the first known keyword, so
\"open chatgpt and get prompt ...\" targets \"chatgpt\" instead of the
whole sentence. The keyword DB is user-editable (brain/keywords.json).
"""

import json

from brain.wordfinder import (
    DEFAULT_KEYWORDS,
    add_keyword,
    find_target_keyword,
    get_keywords,
)


class TestFindTargetKeyword:
    def test_single_word_prefix(self):
        """A known keyword at the start of the target words is returned."""
        assert find_target_keyword(
            ["chatgpt", "and", "get", "prompt"], frozenset({"chatgpt"})
        ) == ("chatgpt", 1)

    def test_longest_match_wins(self):
        """Multi-word keywords beat their single-word prefixes."""
        assert find_target_keyword(
            ["chat", "gpt", "logo"], frozenset({"chat gpt", "chat"})
        ) == ("chat gpt", 2)

    def test_no_match_returns_none(self):
        """Unrecognised targets are left untouched."""
        assert find_target_keyword(
            ["visual", "studio", "code"], frozenset({"chatgpt"})
        ) is None

    def test_multiword_keyword_must_be_a_prefix(self):
        """'file explorer' matches only when it starts the target words."""
        assert find_target_keyword(
            ["file", "explorer", "settings"], frozenset({"file explorer"})
        ) == ("file explorer", 2)
        assert find_target_keyword(
            ["settings", "file", "explorer"], frozenset({"file explorer"})
        ) is None

    def test_keyword_longer_than_words_does_not_match(self):
        assert find_target_keyword(["chatgpt"], frozenset({"chat gpt"})) is None

    def test_punctuation_on_word_is_ignored(self):
        assert find_target_keyword(
            ["chatgpt,", "make", "logo"], frozenset({"chatgpt"})
        ) == ("chatgpt", 1)


class TestKeywordDb:
    def test_defaults_always_present(self):
        """Built-in AI names work before the user file exists."""
        keywords = get_keywords()
        assert "chatgpt" in keywords
        assert "gemini" in keywords

    def test_defaults_are_a_subset_of_active_keywords(self):
        assert DEFAULT_KEYWORDS <= get_keywords()

    def test_user_file_merges_with_defaults(self, monkeypatch, tmp_path):
        """brain/keywords.json entries are merged with the defaults."""
        from brain import wordfinder

        user_file = tmp_path / "keywords.json"
        user_file.write_text(
            json.dumps({"keywords": ["telegram", "whatsapp"]}), encoding="utf-8"
        )
        monkeypatch.setattr(wordfinder, "KEYWORDS_FILE", user_file)
        monkeypatch.setattr(wordfinder, "_keywords_cache", None)

        keywords = get_keywords()
        assert "telegram" in keywords
        assert "whatsapp" in keywords
        assert "chatgpt" in keywords  # defaults still active

    def test_add_keyword_writes_user_file(self, monkeypatch, tmp_path):
        """'python -m brain.wordfinder add X' persists X and activates it."""
        from brain import wordfinder

        user_file = tmp_path / "keywords.json"
        monkeypatch.setattr(wordfinder, "KEYWORDS_FILE", user_file)
        monkeypatch.setattr(wordfinder, "_keywords_cache", None)

        assert add_keyword("Telegram") is True
        assert user_file.exists()
        data = json.loads(user_file.read_text(encoding="utf-8"))
        assert "telegram" in data["keywords"]
        assert "telegram" in get_keywords()

    def test_add_keyword_rejects_empty(self, monkeypatch, tmp_path):
        from brain import wordfinder

        monkeypatch.setattr(wordfinder, "KEYWORDS_FILE", tmp_path / "keywords.json")
        monkeypatch.setattr(wordfinder, "_keywords_cache", None)
        assert add_keyword("   ") is False
        assert not (tmp_path / "keywords.json").exists()


class _FakeKnowledgeManager:
    """Minimal KnowledgeManager stand-in: only load_applications is used."""

    def __init__(self, applications):
        self._applications = applications

    def load_applications(self):
        return self._applications


class TestLearnedAppKeywords:
    """Keywords are learned automatically from scanned applications."""

    def test_scanned_app_names_and_aliases_are_keywords(self):
        fake = _FakeKnowledgeManager(
            [
                {"name": "Telegram", "aliases": ["tg"]},
                {"name": "Visual Studio Code", "aliases": ["vscode", "code"]},
                {"name": "Google Chrome", "aliases": ["chrome", "google chrome"]},
            ]
        )
        keywords = get_keywords(manager=fake)
        assert "telegram" in keywords
        assert "tg" in keywords
        assert "visual studio code" in keywords
        assert "vscode" in keywords
        assert "chrome" in keywords

    def test_learned_app_keyword_truncates_open_target(self):
        """A learned app name stops the 'open ...' target like any keyword."""
        fake = _FakeKnowledgeManager([{"name": "Telegram", "aliases": []}])
        keywords = get_keywords(manager=fake)
        assert find_target_keyword(
            ["telegram", "and", "get", "messages"], keywords
        ) == ("telegram", 1)

    def test_broken_knowledge_is_graceful(self):
        """A failing knowledge layer contributes nothing, never crashes."""

        class BrokenManager:
            def load_applications(self):
                raise RuntimeError("knowledge unavailable")

        keywords = get_keywords(manager=BrokenManager())
        assert "chatgpt" in keywords  # static defaults still active

    def test_empty_applications_learns_nothing_extra(self):
        keywords = get_keywords(manager=_FakeKnowledgeManager([]))
        assert "chatgpt" in keywords
        assert "zzzz-no-such-app" not in keywords
