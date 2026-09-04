# Changelog

All notable changes to Sarthi are documented here. The current codebase has
moved beyond the last released version (`1.0.4`, see `pyproject.toml`); the
changes below are verifiable from the repository state. Earlier history is
in the git log.

## [Unreleased]

### Added

- **Browser Awareness skill** (`skills/browser_awareness/`) — inspect
  arbitrary websites in an isolated Chrome session; Hermes observes the
  page snapshot and recommends one action, which passes a pure validation
  gate before a safe executor performs it (`navigate/click/type/select/
  check/uncheck/submit/scroll` only). Test-mode planning, no browser
  required.
- **Hermes tool bridge** (`hermes/tool_registry.py`, `hermes/tool_planner.py`) —
  Hermes may request registered tools (`open_app`, `open_website`, `github`,
  `personal_context`); arguments are validated and the tool loop is bounded
  (`MAX_TOOL_CALLS_PER_TASK`). Hermes never executes code or touches the
  filesystem directly.
- **Hermes sandbox** (`hermes/sandbox.py`) — every Hermes task is persisted
  under `sandbox/tasks/<task_id>/` and indexed by query in `sandbox/index.json`.
- **Connectors** (`connectors/`) — `BaseConnector` interface, registry, and a
  Google Calendar OAuth2 connector with `/connectors/*` API routes.
- **Application categorization** — applications.json v2 schema
  (`favourite` / `ignored` / `unattended`); new apps land in `unattended` and
  the UI prompts the user; `/applications/categorize`, `/applications/run`,
  `/applications/categories`, `/applications/favourites` endpoints.
- **Conversation memory** — `knowledge/memory.py` (`/remember`, `/recall`,
  `/forget`), persisted chat transcripts (`/chat`), and per-session Hermes
  conversation history (`hermes/conversation.py`).
- **Chat modes** (`brain/modes.py`) — conversation mode routes every input to
  Hermes chat (no task execution); `/mode` API endpoints.
- **Test runner API** (`/test/prompts`, `/test/run`, `/test-mode`) plus
  hardware telemetry (`utils/telemetry.py`) and `/system/metrics`.
- **CI pipeline** (`.github/workflows/ci.yml`) — lint, format check, tests,
  smoke test on push/PR.
- **Hermes provider abstraction** — Hermes core talks to adapters through a
  small provider interface: `ModelRequest` (provider-neutral request built
  from a `Task` at the manager boundary) in, `ProviderResponse` out.
  `ModelCapabilities` declare what an adapter actually honors
  (structured_output, vision, tool_calling, streaming, context_window).
  Providers are picked by configuration via `hermes/providers/registry.py`:
  `ollama`/`local`, `openrouter`, or `openai_compatible`/`openai` (any
  `/v1`-compatible endpoint — OpenAI, LM Studio, vLLM, ...). Remote
  providers keep the automatic local Ollama fallback; local mode has none.
- **OpenAI-compatible adapter** — `OpenAICompatibleProvider` maps
  `ModelRequest` to `/chat/completions` and maps failures (timeout, HTTP,
  malformed payloads, refused/null content, missing endpoint) to graceful
  `ProviderResponse`s; keyless local servers work without an auth header.
  `OpenRouterProvider` is now a thin subclass (own endpoint/key/headers).
- **`GET /hermes/status`** — diagnostic endpoint reporting the active
  provider, model, capabilities, and fallback (no secrets).
- **Pre-commit hooks** (`.pre-commit-config.yaml`) — no-database-files guard,
  ruff lint/format, smoke test.

### Changed

- **Provider selection is config-driven** — `hermes/main.py` and
  `hermes/service.py` no longer choose providers in code; they delegate to
  the registry. Unknown `HERMES_PROVIDER` values now fall back to the safe
  local provider with a logged warning (previously anything non-local
  silently meant OpenRouter).
- **Browser Awareness / ai_chain decoupled from concrete providers** — the
  default observation/extraction model is built through the provider
  registry (`create_local_provider`) instead of importing
  `LocalHermesProvider` directly; both still accept an injected provider.
- **Local provider JSON mode** — `ModelRequest.structured_output` maps to
  Ollama's `format=json` and an OpenAI-compatible
  `response_format=json_object`; Hermes always parses + validates JSON
  regardless of the flag.
- **Wake word removed** — `wakeword.py`, `variable.py`, `wakeword.bat`,
  `speech/wake_word.py`, the `SPEECH_RECOGNIZED`/wake-word events, the
  `start.bat` wake-word launch, and `tests/test_wake_word.py` were deleted;
  `skills/speech` no longer depends on the removed module.

- **Scanner relocated** — application discovery moved from `knowledge/scanners/`
  to the `skills/scanner/` skill; `KnowledgeManager.refresh_applications()`
  delegates to `scan_all()` and persists via `merge_scan_results()`.
- **EntityResolver relocated** — canonical location is `knowledge/entity_resolver.py`;
  the `brain/resolver.py` / `brain/entity_resolver.py` shims were removed.
- **Skill discovery consolidated** — `skills/registry.py` is the single
  discovery mechanism; the legacy `skills/manager.py` was removed.
- **Deprecated code removed** — `brain/normalizer.py`, the `actions/` package,
  `models/intent.py`, and `knowledge/scanners/` shims were deleted.
- **Local provider resilience** — `LocalHermesProvider` retries once on a pure
  connection timeout (cold model loads) and uses a dedicated 180s
  `LOCAL_HERMES_TIMEOUT`; UI fetch aborts raised to 300s.
- **Sandbox cleanup** — `/clean` handler and `scripts/clean_sandbox.py` keep
  failed tasks for review and prune index records of deleted successes.
- **CORS tightened** — API only allows the local UI origins
  (`127.0.0.1:8000`, `localhost:8000`, `127.0.0.1:5500`, `localhost:5500`).

### Fixed

- `api.py` import ordering — browser/Hermes routers now register when the
  module is imported (not only under `__main__`).
- `.gitignore` no longer excludes `.env.example` (the template file
  contributors are told to copy is trackable again).
- `/websites/search-and-save` — the "search on browser" fallback now persists
  the site to `websites.json` so the next `open <name>` opens it directly.

### Planned (not yet implemented)

- Hermes skill authoring — validated creation/registration of new skills by
  Hermes (see `CONTRIBUTING.md`, "Hermes Contribution Boundary").
- Vision package, multi-agent, plugin marketplace, additional connectors
  (email/IoT), and more entity types (devices, contacts).