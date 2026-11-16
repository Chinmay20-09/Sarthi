"""Tests for the Windows desktop client's narrow local action route."""

from sarthi_client import app_inventory, local_router


def test_explicit_unique_app_launch_uses_local_hand(monkeypatch, tmp_path):
    launched = []
    app_path = str(tmp_path / "Calculator.lnk")
    monkeypatch.setattr(local_router, "IS_WINDOWS", True)
    monkeypatch.setattr(local_router, "resolve_application", lambda name: ("Calculator", app_path))
    monkeypatch.setattr(
        local_router.LocalDesktopHand,
        "open_application",
        lambda _self, path: launched.append(path),
    )

    result = local_router.route_local_query("open calc")

    assert result["success"] is True
    assert result["routing"] == "desktop_local"
    assert launched == [app_path]


def test_compound_or_unrecognized_requests_are_deferred(monkeypatch):
    monkeypatch.setattr(local_router, "IS_WINDOWS", True)
    calls = []
    monkeypatch.setattr(local_router, "resolve_application", lambda name: calls.append(name))

    assert local_router.route_local_query("open calc and open notepad") is None
    assert local_router.route_local_query("please open calc") is None
    assert calls == []


def test_unknown_application_is_deferred(monkeypatch):
    monkeypatch.setattr(local_router, "IS_WINDOWS", True)
    monkeypatch.setattr(local_router, "resolve_application", lambda _name: None)

    assert local_router.route_local_query("open unknown app") is None


def test_stale_inventory_launch_path_returns_failure(monkeypatch):
    monkeypatch.setattr(local_router, "IS_WINDOWS", True)
    monkeypatch.setattr(
        local_router,
        "resolve_application",
        lambda _name: ("Calculator", "C:/missing/Calculator.lnk"),
    )

    result = local_router.route_local_query("open calculator")

    assert result["success"] is False
    assert result["routing"] == "desktop_local"


def test_device_inventory_rejects_duplicate_names(monkeypatch, tmp_path):
    monkeypatch.setattr(app_inventory, "inventory_path", lambda: tmp_path / "device.db")
    monkeypatch.setattr(
        app_inventory,
        "_discover",
        lambda: [
            ("Editor", str(tmp_path / "one" / "editor.exe")),
            ("Editor", str(tmp_path / "two" / "editor.exe")),
        ],
    )

    assert app_inventory.resolve_application("editor") is None


def test_device_inventory_resolves_unique_exact_entry(monkeypatch, tmp_path):
    launch_path = str(tmp_path / "Calculator.lnk")
    monkeypatch.setattr(app_inventory, "inventory_path", lambda: tmp_path / "device.db")
    monkeypatch.setattr(app_inventory, "_discover", lambda: [("Calculator", launch_path)])

    assert app_inventory.resolve_application("calculator") == ("Calculator", launch_path)
