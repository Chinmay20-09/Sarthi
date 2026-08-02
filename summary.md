# Session Summary — Hermes Agent Development

> Date: 2026-08-02
> Project: Sarthi — Local-First AI Desktop Assistant

---

## Overview

This session covered the early milestones of the **Hermes Agent** (Sarthi's AI execution layer):
foundation work, the provider framework, configuration package, and the first real AI
integration with **OpenRouter**. It also included a cleanup pass that removed the project's
pre-commit hook configuration.

---

## 1. Pre-commit Removal

Removed all pre-commit tooling from the repository:

- **Deleted** `.pre-commit-config.yaml` (ruff / mypy / file-hygiene hooks)
- **Deleted** `.git/hooks/pre-commit` (the installed git hook)
- **Updated** `README.md` — removed all pre-commit references:
  - Dev-deps install step (`pip install ruff mypy pre-commit` → `pip install ruff mypy`)
  - Advisory mypy line (`pre-commit run --hook-stage manual mypy` → `mypy .`)
  - The entire "Pre-commit Hooks" section + table
  - Roadmap row and Contributing list (renumbered to 1–5)

Ruff and mypy configs in `pyproject.toml` were **kept** (they are standalone dev tools).

---

## 2. Phase 2.1 — Provider Framework (architecture only)

Created the provider framework (`hermes/providers/`):

- `base.py` — `ProviderResponse` dataclass (`success`, `provider`, `model`, `text`, `error`)
  and abstract `AIProvider` base exposing `generate(prompt)`
- `exceptions.py` — `ProviderError` → `ProviderUnavailable`, `InvalidResponse`
- `openrouter_provider.py` — stub provider returning `ProviderResponse(success=True, ...)`
- `manager.py` — `ProviderManager` with `initialize(provider)` and `generate()` delegation
- `__init__.py` — public exports

No networking, no deps, no env vars (per phase spec).

---

## 3. Rename: `generate(prompt)` → `generate(task)`

- Renamed the parameter across `base.py`, `openrouter_provider.py`, and `manager.py`
- Aligned the parameter type to `HermesTask` (then `Task`) so the whole chain is type-consistent
- Fixed a missing trailing newline (W292) in `hermes/orchestrator.py`

---

## 4. Configuration Package

Created `hermes/config/`:

- `settings.py` — `HermesConfig` dataclass (expanded over phases)
- `loader.py` — `ConfigLoader` (stub initially, later real `.env` loading)
- `__init__.py` — exports
- Deleted the old `hermes/config.py` (verified unreferenced)

---

## 5. Phase 2.2 — OpenRouter Integration

The first real AI integration. `python -m hermes.main` now runs a complete flow:
load config → read API key from `.env` → init provider → send one test task →
receive a real response → save to sandbox → exit gracefully.

### Model / Task

- `hermes/models.py` — `Task` dataclass (`id`, `prompt`, `task_type`, `context`);
  replaced `HermesTask` everywhere
- Test task: `Task(id="task_000001", prompt="Introduce yourself as Hermes in one paragraph.", task_type="test")`

### Configuration (all in one place)

`HermesConfig` exposes: `provider`, `model` (`openai/gpt-5`), `temperature`, `timeout`,
`sandbox_path`, `api_key`, `http_referer`, `x_title`.

`ConfigLoader` is the **only** module that reads environment variables — it loads `.env`
(pinned to project root) and reads `OPENROUTER_API_KEY`, `OPENROUTER_HTTP_REFERER`,
`OPENROUTER_X_TITLE`.

### Provider

`OpenRouterProvider` is a real HTTP client (httpx):

- `POST https://openrouter.ai/api/v1/chat/completions`
- Headers: `Authorization: Bearer <key>`, `Content-Type`, `HTTP-Referer`, `X-Title`
- `stream: False`, no retries, no fallback
- **Never throws** — every code path returns a `ProviderResponse`:
  - Missing API key, connection timeout, HTTP status with human-readable reason phrase
    (e.g. `HTTP 402 Payment Required`), invalid response shape, and an `Exception`
    catch-all ("Unexpected error")

### Sandbox

`TaskSandbox` writes to `sandbox/tasks/task_000001/`:

- `prompt.md`
- `response.md` (response text, or error text on failure)
- `metadata.json` — `task_id`, `provider`, `model`, `status`, `timestamp` (UTC), `duration_ms`

Dead code cleanup: removed the unused `next_task_id()` method from `TaskSandbox`
(main hardcodes `id="task_000001"` per spec) and the old `ensure_sandbox()` helper.

### Main flow

`hermes/main.py` prints the spec's console sequence and calls `main()` under `__main__`.
Architecture: `main → HermesOrchestrator → ProviderManager → OpenRouterProvider`
(only the provider performs networking).

### Dependencies

- Installed `httpx` and `python-dotenv`; added both to `pyproject.toml` dependencies

### Validation

- Ruff lint + format pass (15 files)
- Mocked provider tests: missing key, timeout, HTTP 401/402, invalid shape, catch-all, headers/payload
- Real run: **`python -m hermes.main` completed end-to-end**
  - Result: `HTTP 402 Payment Required` from OpenRouter for `openai/gpt-5`
  - Verified `openai/gpt-5` is a **valid model slug** (present in OpenRouter's 337-model catalog)
  - Conclusion: 402 is an **account credits/access issue**, not a code bug — the framework
    handled it gracefully exactly per spec (no traceback, error saved to sandbox)

---

## Current Hermes Architecture

```
hermes/
├── __init__.py
├── client.py            # (pre-existing stub, unused)
├── config/
│   ├── __init__.py
│   ├── loader.py        # ConfigLoader — only module reading env
│   └── settings.py      # HermesConfig — single source of config
├── main.py              # full execution flow
├── models.py            # Task
├── orchestrator.py      # HermesOrchestrator
├── prompt_builder.py    # (pre-existing, unused)
├── providers/
│   ├── __init__.py
│   ├── base.py          # AIProvider, ProviderResponse
│   ├── exceptions.py
│   ├── manager.py       # ProviderManager
│   └── openrouter_provider.py  # real OpenRouter httpx client
└── sandbox.py           # TaskSandbox
```

---

## Known Limitations

- Single provider (OpenRouter), no provider selection/switching
- No retries, streaming, validation, queue, offline mode, memory, or caching
- `except Exception` catch-all is silent (no logging)
- Real success depends on OpenRouter account credits for `openai/gpt-5`
- `prompt_builder.py` and `client.py` remain pre-existing and unused
- No unit test files committed for the Hermes package yet

---

## Next Steps (proposed)

1. **Validation Layer** (next milestone) — validate task + response before/after processing
2. Add `tests/` coverage for provider, config loader, and sandbox
3. Add logging inside the provider catch-all for diagnosability
4. Implement provider selection in `ProviderManager` using `HermesConfig.provider`
5. Top up OpenRouter credits and re-run `python -m hermes.main` to confirm a real LLM response

---

## Blocked Features

Offline Queue · Local Provider · Retry Logic · Streaming · Memory ·
Skill Installation · Task Scheduler
