"""Tests for launcher-side Ollama discovery and startup decisions."""

from types import SimpleNamespace

from scripts import ensure_ollama


def test_remote_ollama_url_does_not_start_local_service(monkeypatch, capsys):
    monkeypatch.setattr(
        ensure_ollama.ConfigLoader,
        "load",
        lambda _self: SimpleNamespace(local_hermes_url="https://ollama.example.test"),
    )
    monkeypatch.setattr(
        ensure_ollama,
        "_read_tags",
        lambda _url: (_ for _ in ()).throw(AssertionError("remote URL must not be probed")),
    )

    assert ensure_ollama.ensure_ollama() == 0
    assert "not starting a local service" in capsys.readouterr().out


def test_local_ollama_is_started_and_ready_model_is_reported(monkeypatch, capsys):
    config = SimpleNamespace(local_hermes_url="http://localhost:11434")
    monkeypatch.setattr(ensure_ollama.ConfigLoader, "load", lambda _self: config)
    tags = iter([None, {"hermes3:8b-llama3.1-q3_K_M"}])
    monkeypatch.setattr(ensure_ollama, "_read_tags", lambda _url: next(tags))
    monkeypatch.setattr(ensure_ollama, "_ollama_executable", lambda: "ollama.exe")
    started = []
    monkeypatch.setattr(ensure_ollama, "_start_ollama", lambda exe, url: started.append((exe, url)))
    monkeypatch.setattr(ensure_ollama.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        ensure_ollama, "_model_for_active_profile", lambda _config: "hermes3:8b-llama3.1-q3_K_M"
    )

    assert ensure_ollama.ensure_ollama() == 0
    assert started == [("ollama.exe", "http://localhost:11434")]
    output = capsys.readouterr().out
    assert "Starting Ollama service" in output
    assert "is installed" in output


def test_missing_model_is_reported_without_automatic_download(monkeypatch, capsys):
    monkeypatch.setattr(
        ensure_ollama.ConfigLoader,
        "load",
        lambda _self: SimpleNamespace(local_hermes_url="http://127.0.0.1:11434"),
    )
    monkeypatch.setattr(ensure_ollama, "_read_tags", lambda _url: {"other-model:latest"})
    monkeypatch.setattr(ensure_ollama, "_model_for_active_profile", lambda _config: "hermes3:8b")

    assert ensure_ollama.ensure_ollama() == 0
    output = capsys.readouterr().out
    assert "Model 'hermes3:8b' is not installed" in output
    assert "ollama pull hermes3:8b" in output
