"""Tests for the low/medium/high local inference setting."""

import pytest
from fastapi import HTTPException

from api import SettingRequest, get_setting, save_setting
from hermes.config.model_profiles import MODEL_PROFILES
from hermes.config.settings import HermesConfig
from hermes.providers.local_provider import LocalHermesProvider


class _MemorySettingsDb:
    def __init__(self, value=None):
        self.value = value
        self.saved = None

    def fetch_one(self, _sql, _params):
        return {"value": self.value} if self.value else None

    def execute(self, _sql, params):
        self.saved = params
        self.value = params[1]


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_existing_settings_api_persists_allowed_model_profiles(monkeypatch, profile):
    from database import manager

    db = _MemorySettingsDb()
    monkeypatch.setattr(manager, "get_database", lambda: db)
    result = save_setting(SettingRequest(key="hermes_model_profile", value=profile))
    assert result["success"] is True
    assert db.value == profile


def test_settings_api_rejects_unknown_model_profile(monkeypatch):
    from database import manager

    db = _MemorySettingsDb()
    monkeypatch.setattr(manager, "get_database", lambda: db)
    with pytest.raises(HTTPException) as exc:
        save_setting(SettingRequest(key="hermes_model_profile", value="custom-path"))
    assert exc.value.status_code == 422
    assert db.saved is None


def test_model_profile_setting_defaults_to_configured_low(monkeypatch):
    from database import manager

    monkeypatch.setattr(manager, "get_database", lambda: _MemorySettingsDb())
    result = get_setting("hermes_model_profile")
    assert result["value"] == "low"


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_saved_profile_controls_next_local_model_request(monkeypatch, profile):
    from database import manager

    db = _MemorySettingsDb(profile)
    monkeypatch.setattr(manager, "get_database", lambda: db)
    provider = LocalHermesProvider(HermesConfig())
    assert provider.model == MODEL_PROFILES[profile]["model"]
