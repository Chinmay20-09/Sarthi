"""Regression tests for entity resolver matching quality.

The resolver must reject nonsense inputs (e.g. "hello") instead of
latching onto unrelated entities through WRatio's partial scoring,
while still resolving real apps/websites — including via aliases
("chrome" -> Google Chrome) and common typos ("spotfy" -> Spotify).
"""

import pytest

from knowledge.entity_resolver import EntityResolver


@pytest.fixture
def resolver():
    """A resolver with a mix of real entities and PATH-scan junk names."""
    return EntityResolver(
        entities=[
            {"name": "Google Chrome", "aliases": ["chrome", "google chrome"], "category": "applications"},
            {"name": "Spotify", "aliases": ["spotify"], "category": "applications"},
            {"name": "GitHub", "aliases": ["github", "git hub"], "category": "websites"},
            {"name": "YouTube", "aliases": ["youtube", "you tube"], "category": "websites"},
            {"name": "Google", "aliases": ["google", "search"], "category": "websites"},
            {"name": "Code", "aliases": ["code", "vs code", "vscode"], "category": "applications"},
            # Junk utilities (as found on PATH) that must never win a match
            {"name": "ShellMcpServers.Packaging", "aliases": [], "category": "applications"},
            {"name": "MEM", "aliases": [], "category": "applications"},
            {"name": "timeout", "aliases": [], "category": "applications"},
            {"name": "SP", "aliases": [], "category": "applications"},
            {"name": "VOLUNTEER", "aliases": [], "category": "applications"},
            {"name": "SETVM", "aliases": [], "category": "applications"},
            {"name": "Rar", "aliases": [], "category": "applications"},
        ]
    )


class TestNonsenseRejected:
    """Nonsense inputs must stay unresolved, not fuzzy-match to real apps."""

    @pytest.mark.parametrize(
        "text",
        [
            "hello",
            "random nonsense",
            "set volume to 50",
            "what time is it",
            "time it",  # the interpreter-extracted target of "what time is it"
            "how are you today",
            "good morning",
            "tell me a joke",
        ],
    )
    def test_nonsense_not_resolved(self, resolver, text):
        assert resolver.resolve(text) == text
        assert resolver.resolve_entity(text) is None


class TestLegitResolutions:
    """Real entities must still resolve, including via aliases."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("open chrome", "open Google Chrome"),  # via alias, not junk MEM
            ("open google", "open Google"),
            ("open youtube", "open YouTube"),
            ("open git hub", "open GitHub"),  # multi-word alias
            ("open vs code", "open Code"),  # alias "vs code"
            ("open vscode", "open Code"),  # alias "vscode"
            ("launch spotify", "launch Spotify"),
        ],
    )
    def test_resolves_to_entity(self, resolver, text, expected):
        assert resolver.resolve(text) == expected

    def test_typo_still_matches(self, resolver):
        # "spotfy" is a typo of Spotify — fuzzy matching must still work
        assert resolver.resolve("open spotfy") == "open Spotify"


class TestJunkNeverWins:
    """Short PATH utilities must never capture a longer, legitimate phrase."""

    def test_full_word_not_attached_to_short_junk(self, resolver):
        # WRatio partial scoring wants "spotify" -> "SP"; the length guard stops it
        assert resolver.resolve("launch spotify") == "launch Spotify"

    def test_short_phrase_not_attached_to_long_junk(self, resolver):
        # "hello" contains the "hell" substring of "ShellMcpServers.Packaging"
        assert resolver.resolve("hello") == "hello"

    def test_exact_single_word_match_still_works(self, resolver):
        # Matching a name that happens to be short is fine when it's exact
        result = resolver.resolve("open github")
        assert result == "open GitHub"


class TestNameBeatsAlias:
    """An exact name match must win over a colliding alias."""

    def test_website_name_not_shadowed_by_app_alias(self):
        resolver = EntityResolver(
            entities=[
                {"name": "Google", "aliases": ["search"], "category": "websites"},
                # An app whose generated alias collides with the website's name
                {"name": "ChromeHelper", "aliases": ["google"], "category": "applications"},
            ]
        )
        assert resolver.resolve("open google") == "open Google"

    def test_canonical_name_wins_over_alias_of_same_entity(self):
        resolver = EntityResolver(
            entities=[
                {"name": "Spotify", "aliases": ["spotify"], "category": "applications"},
            ]
        )
        result = resolver.resolve("open spotify")
        assert result == "open Spotify"
