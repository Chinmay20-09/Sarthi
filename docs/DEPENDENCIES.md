# Dependency audit (observed)

Sources: `pyproject.toml`, actual imports in `Backend/` and
`Desktop/client/`, and the test suite. Nothing was installed or removed.

## Runtime dependencies (pyproject [project.dependencies])

| Package | Declared | Actually imported by | Verdict |
| --- | --- | --- | --- |
| fastapi | yes | api.py, routes | runtime |
| uvicorn | yes | api.py server start, sarthi.bat background mode | runtime |
| httpx | yes | Desktop client backend.py, project_tracker github/notion, connectors | runtime |
| python-dotenv | yes | hermes/config/loader.py | runtime |
| pystray | yes | **no import found anywhere** | apparently unused |
| pillow | yes | api.py (dashboard image generation in test runner) | runtime |
| psutil | yes | hands/desktop/processes.py, scanner, reading.py, telemetry | runtime |
| rapidfuzz | yes | knowledge/entity_resolver.py (+ retriever) | runtime |
| google-auth-oauthlib | yes | connectors/google_calendar/auth | runtime |

## Optional extra `automation` (laptop control, lazily imported)

| Package | Imported by | Verdict |
| --- | --- | --- |
| pyautogui≥0.9.54 | ai_chain/control.py, hands/desktop/input.py, browser_automation fallback paths | optional runtime |
| keyboard≥0.13.5 | ai_chain/control.py (abort hotkey) | optional runtime |
| pyperclip≥1.8 | ai_chain/control.py, hands/desktop/input.py | optional runtime |
| pywin32≥306 | utils/voice.py (SAPI TTS), hands/desktop/windows.py | optional runtime (voice degrades to PowerShell without it) |

## Optional extra `browser` (DOM stacks, lazily imported)

| Package | Imported by | Verdict |
| --- | --- | --- |
| selenium≥4.20 | browser_awareness/driver+inspector+selenium_page, ai_chain/dom+selenium_dom+browser_automation | optional runtime |
| beautifulsoup4≥4.12 | same modules (regex fallback exists without it) | optional runtime |
| playwright≥1.40 | fallback backends in both stacks | optional runtime |

## Speech stack (NOT declared)

| Package | Imported by | Verdict |
| --- | --- | --- |
| sounddevice | speech/recorder.py | undeclared runtime dep of the voice CLI / /listen |
| faster-whisper | speech/speech_to_text.py | undeclared runtime dep (lazy import) |
| numpy (transitively) | via whisper stack | transitively required for voice |

## Dev dependencies ([project.optional-dependencies].dev)

| Package | Used by | Verdict |
| --- | --- | --- |
| ruff | lint/format config in pyproject | dev |
| pytest | tests/ | dev |

**Also observed in the environment but not declared**: pytest-cov plugins not
present; `httpx2` referenced only by a starlette deprecation warning (not a
dependency of this project).

## System dependencies

- **Ollama** (local LLM) — default `HERMES_PROVIDER=local`; runtime-checked,
  graceful fallback errors.
- **Chrome** — browser awareness + ai_chain automation (Selenium Manager
  fetches the matching chromedriver automatically).
- **Windows** — TTS (SAPI/PowerShell), Desktop hand (pywin32/pygetwindow),
  ai_chain laptop control. Non-Windows degrades (voice → log line) or is
  unsupported (desktop hand actions).
- **Microphone + Whisper model files** — voice input only.

## Client (Desktop) dependencies

tkinter (stdlib) + httpx only — verified: `Desktop/client/sarthi_client/`
imports nothing else from third parties.

## Summary counts

- declared runtime: 9 (1 apparently unused: pystray)
- declared optional: automation 4, browser 3
- undeclared-but-imported: sounddevice, faster-whisper (voice features)
- dev: 2
- system: Ollama, Chrome, Windows audio/TTS
