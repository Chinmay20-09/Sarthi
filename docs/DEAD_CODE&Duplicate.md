# Dead code (observed)

Suspected dead or orphaned systems. **Nothing was deleted** — source is
untouched. Confidence reflects the strength of the caller/import evidence.

## 1. `ai_chain/browser_automation.py` + `run_browser_chain` (v1.7 DOM engine)

- **Path**: `skills/automation_engine/ai_chain/browser_automation.py`
  (exported via `ai_chain/__init__.py`)
- **Purpose**: fully DOM-driven multi-site browser chains (navigate/click/
  copy/paste with verification and ChainState).
- **Evidence**: no caller outside its own module and tests. `run_browser_chain`
  appears nowhere in production code (repo-wide grep). The production chain
  (`chain.py`) uses `WebAiDriver` + `dom.py` instead.
- **Imports**: exported in `ai_chain/__init__.py::__all__`; used by
  `tests/test_browser_automation.py`.
- **Tests**: extensive (test_browser_automation.py) — so it is maintained but
  unused in production.
- **Confidence**: HIGH (as *production-dead*; it is a live library).

## 2. `pystray` dependency

- **Path**: `pyproject.toml` [project.dependencies]
- **Purpose**: system tray icon (presumed from the name).
- **Evidence**: no `import pystray` anywhere in Backend/, Desktop/, tests.
- **Confidence**: HIGH (unused import-wise; may be a leftover from a removed
  tray feature).

## 3. `AutomationEngine.run(event)` pipeline

- **Path**: `skills/automation_engine/engine.py`
- **Purpose**: event-driven assistant coordination (ProjectScanner,
  PreviewGenerator, AutomationEvent).
- **Evidence**: only `register_assistant` + BrainAssistant are used by
  `skill.py`; nothing constructs `AutomationEvent` or calls `run()` outside
  the engine module itself.
- **Confidence**: MEDIUM (scaffolding for a future flow; imports resolve).

## 4. `analyze` command branch (automation skill)

- **Path**: `skills/automation_engine/skill.py:79-80,171-180`
- **Purpose**: "analyze skill capabilities".
- **Evidence**: returns a fixed stub `{capabilities: []}` — no analysis.
- **Confidence**: HIGH (stub, not dead code — dead path in a live file).

## 5. `/browser/action` endpoint

- **Path**: `skills/browser/routes.py:29` + `service.py::execute_action`
- **Purpose**: browser extension action channel.
- **Evidence**: prints and returns `{"status": "pending"}`; no extension
  exists in the repo; no UI caller found.
- **Confidence**: HIGH (placeholder; the page/selection GET endpoints have no
  in-repo consumer either).

## 6. `main-test.py`

- **Path**: `Backend/main-test.py`
- **Purpose**: manual smoke check.
- **Evidence**: not referenced by tests or docs; standalone by design.
- **Confidence**: LOW (intentional manual tool; kept out of pytest).

## 7. `hermes/main.py` standalone loop

- **Path**: `Backend/hermes/main.py`
- **Purpose**: single-prompt provider test.
- **Evidence**: no callers; manual diagnostic.
- **Confidence**: LOW (deliberate dev tool).

## 8. `Backend/sandbox/` duplicate task store

- **Path**: `Backend/sandbox/` (index.json + tasks)
- **Purpose**: TaskSandbox output when the server cwd is Backend/.
- **Evidence**: contains real task history; duplicates the root `sandbox/`
  store's role (see DIVERGENCE.md #6). Not dead code, but one of the two
  locations is unintended.
- **Confidence**: MEDIUM (which one is "real" depends on launch mode).

## 9. `_DETERMINISTIC_DOMAINS` partial coverage

- **Path**: `Backend/brain/interpreter.py`
- **Purpose**: whitelist keeping known domains on the fast path.
- **Evidence**: lists only youtube/github/google/stackoverflow; every other
  known website in knowledge/websites.json takes the browse path only when the
  token is a bare domain — named sites ("open youtube") work because they are
  not domains. Behaviour quirk rather than dead code; recorded for review.
- **Confidence**: LOW (design nuance, flagged during audit).

## Not counted (verified alive)

- `hands/desktop/*` — used by the close handler + desktop_agent CLI.
- `utils/telemetry.py`, `reading.py` — used by /test/run and /system/metrics.
- `database/profiles.py` — used by browser_awareness driver.
- `speech/*` — used by /listen and main.py CLI.
# Duplication (observed)

Systems with overlapping responsibilities. Each entry documents the overlap
and the observed relationship — no judgement about which should survive.

## 1. Two model-driven tool loops

- **A**: `hermes/agent.py` HermesAgent loop
- **B**: `hermes/tool_planner.py` + `hermes/orchestrator.py` loop
- **Overlap**: both take a user query, ask the model for a final answer or a
  tool call, execute via `hermes/tool_registry.py`, and iterate.
- **Callers**: A ← /command complexity fallback (`run_task`). B ←
  `POST /hermes/chat`, `hermes/main.py`, and indirectly the NLP fallback's
  provider stack.
- **Relationship**: unclear — B predates A (A is "Phase 3d", B has its own
  bounded-loop contract); both remain wired to production endpoints.

## 2. Two browser automation stacks with DOM reading

- **A**: `skills/browser_awareness/` (Selenium primary / Playwright fallback,
  BeautifulSoup parsing, manager loop)
- **B**: `skills/automation_engine/ai_chain/dom.py` + `selenium_dom.py`
  (Selenium attach / Playwright fallback, BeautifulSoup parsing)
- **Overlap**: both attach to Chrome, read page_source, parse HTML, and
  resolve elements; both implement the same Selenium-primary/Playwright-
  fallback pattern independently.
- **Callers**: A ← browse intent + browser_ask tool. B ← ai_chain driver.
- **Relationship**: parallel implementations of the same capability; ai_chain
  additionally has the v1.7 `browser_automation.py` DOM engine (a third
  variant, see DEAD_CODE.md #1).

## 3. Two "open a website" paths

- **A**: `skills/browser/main.py` — OS default browser via webbrowser.
- **B**: `skills/browser_awareness/` — isolated Chrome with DOM loop.
- **Callers**: A ← executor open handler + OpenWebsiteTool/SearchWebTool.
  B ← browse intent + BrowserAskTool.
- **Relationship**: intentional split (deterministic vs non-deterministic
  domains), decided in the interpreter (`_DETERMINISTIC_DOMAINS`,
  `_extract_bare_domain`). Session/login state differs between them.

## 4. Two conversation persistence tables

- **A**: `chat_messages` — written by `POST /chat` (UI renders first).
- **B**: `conversation_messages` — written by `hermes/conversation.py`.
- **Overlap**: both store role/content session turns; `DELETE /chat` clears
  both for a session.
- **Relationship**: unclear — the UI mirror may exist to render exactly what
  the dashboard displayed (including cards), but the split is undocumented.

## 5. Two sandbox locations (same system, two roots)

- **A**: `Backend/sandbox/` — created when the server runs with Backend/ as
  cwd (sarthi.bat dev mode).
- **B**: `sandbox/` (project root) — when run from the root / pytest.
- **Overlap**: same TaskSandbox code, `HERMES_SANDBOX_PATH` is relative; both
  index.json files exist with different histories.
- **Relationship**: accidental path-resolution artefact, not two designs.

## 6. Two config sources for the API bind address

- **A**: `Backend/config.py` API_HOST/API_PORT (imported by api.py).
- **B**: `sarthi.bat` set lines.
- **Relationship**: transitional; the bat file comments admit the manual sync.

## 7. Two test harnesses

- **A**: pytest suite (tests/).
- **B**: in-app runner `POST /test/run` + test_prompts.json (60 prompts
  through BrainEngine, dry-run mode, hardware telemetry).
- **Relationship**: intentional (B is a smoke/telemetry dashboard), but B is
  untested and duplicates prompt coverage A already has.

## 8. Two GitHub data paths

- **A**: `skills/project_tracker/github.py` — GitHub API client for the
  tracker skill.
- **B**: `hermes/tools/github.py` — Hermes tool exposing GitHub data.
- **Overlap**: both fetch GitHub data for the configured username.
- **Callers**: A ← project_tracker skill sync. B ← Hermes agent.
- **Relationship**: unclear whether B delegates to A (it re-implements a
  thin fetch; both read `settings.github_username`).
