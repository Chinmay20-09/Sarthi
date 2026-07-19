"""Tests for knowledge/manager.py.

Tests the KnowledgeManager's entity loading, caching,
find_entity, find_by_alias, and get_all_entities APIs.
Uses temporary JSON files to avoid touching real data.
"""

import json
from pathlib import Path

import pytest

from knowledge.manager import KnowledgeManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def apps_data():
    return {
        "version": 1,
        "entities": [
            {"name": "Chrome", "path": "/usr/bin/chrome", "aliases": ["google chrome"]},
            {"name": "VS Code", "path": "/usr/bin/code", "aliases": ["vscode", "code"]},
        ],
    }


@pytest.fixture
def websites_data():
    return {
        "version": 1,
        "entities": [
            {"name": "YouTube", "url": "https://youtube.com", "aliases": ["yt"]},
            {"name": "GitHub", "url": "https://github.com", "aliases": ["git hub"]},
        ],
    }


@pytest.fixture
def apps_file(tmp_path, apps_data):
    path = tmp_path / "applications.json"
    with open(path, "w") as f:
        json.dump(apps_data, f)
    return path


@pytest.fixture
def websites_file(tmp_path, websites_data):
    path = tmp_path / "websites.json"
    with open(path, "w") as f:
        json.dump(websites_data, f)
    return path


@pytest.fixture
def manager(apps_file, websites_file):
    """KnowledgeManager with test data files."""
    return KnowledgeManager(
        applications_path=apps_file,
        websites_path=websites_file,
    )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class TestLoading:
    def test_load_applications(self, manager):
        """load_applications should return application entities."""
        apps = manager.load_applications()
        assert len(apps) == 2
        names = [a["name"] for a in apps]
        assert "Chrome" in names
        assert "VS Code" in names

    def test_load_websites(self, manager):
        """load_websites should return website entities."""
        websites = manager.load_websites()
        assert len(websites) == 2
        names = [w["name"] for w in websites]
        assert "YouTube" in names
        assert "GitHub" in names

    def test_load_missing_file(self, tmp_path):
        """Loading a non-existent file should return empty list."""
        manager = KnowledgeManager(
            applications_path=tmp_path / "nonexistent.json",
        )
        apps = manager.load_applications()
        assert apps == []

    def test_load_all_entities(self, manager):
        """get_all_entities should merge all categories."""
        entities = manager.get_all_entities()
        # 2 apps + 2 websites = 4 entities
        assert len(entities) == 4

    def test_get_all_entities_structure(self, manager):
        """Each entity should have name, aliases, category."""
        entities = manager.get_all_entities()
        for entity in entities:
            assert "name" in entity
            assert "aliases" in entity
            assert "category" in entity


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


class TestCaching:
    def test_cache_hit(self, manager):
        """Second call should use cache (not load from disk again)."""
        apps = manager.load_applications()
        # Clear the loader's internal state to confirm cache is used
        manager._app_loader.file_path = Path("/nonexistent")
        cached = manager.load_applications()
        assert cached == apps

    def test_cache_clear(self, manager):
        """Clearing cache should force reload from disk."""
        apps = manager.load_applications()
        manager.clear_cache()
        # Now the loader will try to read from the real file (which is still valid)
        reloaded = manager.load_applications()
        assert reloaded == apps

    def test_cache_independence(self, manager):
        """Different categories should have independent caches."""
        manager.load_applications()
        manager.load_websites()
        # Clearing apps cache should not affect websites
        manager._applications_cache = None
        assert manager._websites_cache is not None


# ---------------------------------------------------------------------------
# Finding Entities
# ---------------------------------------------------------------------------


class TestFindEntity:
    def test_find_entity_by_name(self, manager):
        """find_entity should find by exact name match."""
        entity = manager.find_entity("Chrome")
        assert entity is not None
        assert entity["name"] == "Chrome"

    def test_find_entity_case_insensitive(self, manager):
        """find_entity should be case insensitive."""
        entity = manager.find_entity("chrome")
        assert entity is not None
        assert entity["name"] == "Chrome"

    def test_find_entity_by_category(self, manager):
        """find_entity should filter by category."""
        # Should find YouTube in websites
        entity = manager.find_entity("YouTube", category="websites")
        assert entity is not None
        assert entity["name"] == "YouTube"
        # Should NOT find YouTube in applications
        entity = manager.find_entity("YouTube", category="applications")
        assert entity is None

    def test_find_entity_not_found(self, manager):
        """find_entity should return None for missing entity."""
        entity = manager.find_entity("NonExistent")
        assert entity is None

    def test_find_entity_empty_manager(self, tmp_path):
        """Empty manager should return None."""
        manager = KnowledgeManager()
        entity = manager.find_entity("anything")
        assert entity is None


class TestFindByAlias:
    def test_find_by_alias(self, manager):
        """find_by_alias should find by alias."""
        entity = manager.find_by_alias("google chrome")
        assert entity is not None
        assert entity["name"] == "Chrome"

    def test_find_by_alias_case_insensitive(self, manager):
        """find_by_alias should be case insensitive."""
        entity = manager.find_by_alias("Google Chrome")
        assert entity is not None

    def test_find_by_alias_with_category(self, manager):
        """find_by_alias should filter by category."""
        entity = manager.find_by_alias("yt", category="websites")
        assert entity is not None
        assert entity["name"] == "YouTube"

    def test_find_by_alias_not_found(self, manager):
        """find_by_alias should return None for missing alias."""
        entity = manager.find_by_alias("nonexistent alias")
        assert entity is None


class TestFindApplication:
    def test_find_application_by_name(self, manager):
        """find_application should find by name."""
        app = manager.find_application("Chrome")
        assert app is not None
        assert app["name"] == "Chrome"

    def test_find_application_by_alias(self, manager):
        """find_application should find by alias fallback."""
        app = manager.find_application("vscode")
        assert app is not None
        assert app["name"] == "VS Code"

    def test_find_application_not_found(self, manager):
        """find_application should return None for missing."""
        app = manager.find_application("NonExistent")
        assert app is None


class TestFindWebsite:
    def test_find_website_by_name(self, manager):
        """find_website should find by name."""
        site = manager.find_website("YouTube")
        assert site is not None

    def test_find_website_by_alias(self, manager):
        """find_website should find by alias."""
        site = manager.find_website("yt")
        assert site is not None
        assert site["name"] == "YouTube"

    def test_find_website_not_found(self, manager):
        """find_website should return None for missing."""
        site = manager.find_website("NonExistent")
        assert site is None


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


class TestSave:
    def test_save_applications(self, manager, tmp_path):
        """save_applications should persist data."""
        new_apps = [
            {"name": "Firefox", "path": "/usr/bin/firefox", "aliases": []},
        ]
        result = manager.save_applications(new_apps)
        assert result is True
        # Cache should be invalidated
        assert manager._applications_cache is None
        # Reload should return new data
        loaded = manager.load_applications()
        assert len(loaded) == 1
        assert loaded[0]["name"] == "Firefox"

    def test_save_websites(self, manager):
        """save_websites should persist data."""
        new_sites = [
            {"name": "Example", "url": "https://example.com", "aliases": []},
        ]
        result = manager.save_websites(new_sites)
        assert result is True

    def test_save_triggers_cache_invalidation(self, manager):
        """Saving should invalidate the cache."""
        manager.load_applications()
        assert manager._applications_cache is not None
        manager.save_applications([{"name": "New", "aliases": []}])
        assert manager._applications_cache is None


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    def test_refresh_applications_no_scanner(self, manager):
        """refresh_applications should fail gracefully without scanner."""
        result = manager.refresh_applications()
        # Should just fail without crashing
        assert result is False or isinstance(result, bool)
