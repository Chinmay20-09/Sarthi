"""Tests for knowledge → resolver integration.

EntityResolver lives in knowledge/entity_resolver.py. These tests verify
the full KnowledgeManager → EntityResolver chain against a temporary
knowledge base, so the boundary between the two layers is exercised
without touching the real applications.json.
"""

import json

import pytest

from knowledge.entity_resolver import EntityResolver
from knowledge.manager import KnowledgeManager


@pytest.fixture
def manager(tmp_path):
    """KnowledgeManager backed by small, temporary JSON files."""
    apps_data = {
        "version": 1,
        "entities": [
            {
                "name": "Google Chrome",
                "path": "/usr/bin/chrome",
                "aliases": ["chrome", "google chrome"],
            },
            {
                "name": "Code",
                "path": "/usr/bin/code",
                "aliases": ["vscode", "vs code", "visual studio code"],
            },
        ],
    }
    websites_data = {
        "version": 1,
        "entities": [
            {
                "name": "GitHub",
                "url": "https://github.com",
                "aliases": ["github", "git hub"],
            },
        ],
    }

    apps_file = tmp_path / "applications.json"
    websites_file = tmp_path / "websites.json"
    apps_file.write_text(json.dumps(apps_data), encoding="utf-8")
    websites_file.write_text(json.dumps(websites_data), encoding="utf-8")

    return KnowledgeManager(applications_path=apps_file, websites_path=websites_file)


@pytest.fixture
def resolver(manager):
    """Resolver built from the temporary knowledge base."""
    return EntityResolver(entities=manager.get_all_entities())


class TestKnowledgeToResolverChain:
    """get_all_entities → EntityResolver must resolve real entities."""

    def test_entities_include_apps_and_websites(self, manager):
        entities = manager.get_all_entities()
        categories = {e["category"] for e in entities}
        assert "applications" in categories
        assert "websites" in categories
        # Every entity carries the fields the resolver indexes on.
        for entity in entities:
            assert "name" in entity
            assert "aliases" in entity
            assert "category" in entity

    def test_resolve_app_by_alias(self, resolver):
        assert resolver.resolve("open vscode") == "open Code"

    def test_resolve_website_by_alias(self, resolver):
        assert resolver.resolve("go to git hub") == "go to GitHub"

    def test_unresolvable_text_unchanged(self, resolver):
        assert resolver.resolve("tell me a joke") == "tell me a joke"

    def test_find_application_through_manager(self, manager):
        app = manager.find_application("chrome")
        assert app is not None
        assert app["name"] == "Google Chrome"


class TestRealKnowledgeBase:
    """The knowledge layer must stay usable on a machine with no scan yet.

    applications.json is generated per machine (gitignored, never shipped),
    so a fresh clone starts with an empty application base until the user
    runs the scanner. These tests lock that this state does not crash and
    that websites (which ARE shipped) still resolve.
    """

    def test_empty_applications_do_not_crash(self):
        from knowledge.manager import get_manager

        manager = get_manager()
        apps = manager.load_applications()  # [] on a fresh clone — must not raise
        assert isinstance(apps, list)

    def test_resolution_never_crashes_without_apps(self):
        from knowledge.manager import get_manager

        resolver = EntityResolver(entities=get_manager().get_all_entities())
        # Unresolvable input must pass through unchanged (no crash, no junk match).
        assert resolver.resolve("tell me a joke") == "tell me a joke"
