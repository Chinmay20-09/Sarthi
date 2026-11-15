"""Start the local Ollama service when the backend is configured for it.

This is called by ``sarthi.bat`` before Uvicorn starts. It does not download
models; missing model tags are reported with the exact ``ollama pull`` command.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from hermes.config.loader import ConfigLoader
from hermes.config.model_profiles import DEFAULT_MODEL_PROFILE, MODEL_PROFILES


def _is_loopback(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _model_for_active_profile(config) -> str:
    profile_name = config.local_model_profile or DEFAULT_MODEL_PROFILE
    try:
        from database.manager import get_database

        row = get_database().fetch_one(
            "SELECT value FROM settings WHERE key = ?", ("hermes_model_profile",)
        )
        saved = row["value"] if row else None
        if saved in MODEL_PROFILES:
            profile_name = saved
    except Exception:
        pass
    if profile_name == "high":
        return config.local_model or config.model or MODEL_PROFILES["high"]["model"]
    profile = MODEL_PROFILES.get(profile_name, MODEL_PROFILES[DEFAULT_MODEL_PROFILE])
    return profile["model"]


def _read_tags(url: str) -> set[str] | None:
    try:
        with urlopen(f"{url.rstrip('/')}/api/tags", timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {
            str(model.get("name") or model.get("model"))
            for model in payload.get("models", [])
            if isinstance(model, dict) and (model.get("name") or model.get("model"))
        }
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return None


def _ollama_executable() -> str | None:
    executable = shutil.which("ollama")
    if executable:
        return executable
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _start_ollama(executable: str, url: str) -> None:
    parsed = urlsplit(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11434
    env = os.environ.copy()
    env["OLLAMA_HOST"] = f"{host}:{port}"
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
    subprocess.Popen(
        [executable, "serve"],
        cwd=str(BACKEND_DIR),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=flags,
    )


def ensure_ollama() -> int:
    config = ConfigLoader().load()
    url = (config.local_hermes_url or "").rstrip("/")
    if not url:
        print("[Sarthi] LOCAL_HERMES_URL is empty; skipping local Ollama startup.")
        return 1
    if not _is_loopback(url):
        print(f"[Sarthi] Ollama is configured at {url}; not starting a local service.")
        return 0

    tags = _read_tags(url)
    if tags is None:
        executable = _ollama_executable()
        if not executable:
            print("[Sarthi] Ollama is not reachable and the Ollama executable was not found.")
            print("[Sarthi] Install/start Ollama, then run start.bat again.")
            return 1
        print(f"[Sarthi] Starting Ollama service at {url}...")
        try:
            _start_ollama(executable, url)
        except (OSError, ValueError) as exc:
            print(f"[Sarthi] Could not start Ollama: {exc}")
            return 1
        for _ in range(45):
            time.sleep(1)
            tags = _read_tags(url)
            if tags is not None:
                break
        if tags is None:
            print("[Sarthi] Ollama did not become ready within 45 seconds.")
            return 1
    else:
        print(f"[Sarthi] Ollama service is ready at {url}.")

    model = _model_for_active_profile(config)
    if model not in tags:
        print(f"[Sarthi] Model '{model}' is not installed in Ollama.")
        print(f"[Sarthi] Install it with: ollama pull {model}")
    else:
        print(f"[Sarthi] Model '{model}' is installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(ensure_ollama())
