# Database audit (observed)

> **Canonical model vs implemented scope.** In the target architecture the
> database is persistent system state for Memory, Knowledge, Skills, Tools,
> Capabilities, Providers, Hands and configuration. **Today only part of that
> is real**: the SQLite schema (verified table list below) stores memory,
> conversation, history, settings, project, connector and browser-profile
> state. Skills, tools, capabilities, providers and hands are NOT stored in
> the database — they are code-registered at runtime (`skills/registry.py`,
> `hermes/tool_registry.py`, `hands/desktop/capabilities.py`).

## Primary database — SQLite

- **File**: `Backend/database/sarthi.db` (created on first run;
  `DEFAULT_DB_PATH` in `database/manager.py:36`).
- **Owner**: `DatabaseManager` (`get_database()` singleton), schema in
  `database/models.py` (`CREATE TABLE IF NOT EXISTS`, idempotent init).

### Tables (verified live)

| Table | Purpose | Writers | Readers |
| --- | --- | --- | --- |
| `github_projects` | tracked GitHub repos for project tracking | project_tracker skill sync | project_tracker, /projects |
| `github_summary` | cached GitHub summary data | project tracker | /projects/{id} |
| `projects` | user projects (name, github_url, terminal_path) | /projects API | /projects, project_get tool |
| `settings` | key/value user settings (github_username, voice_replies, ...) | POST /settings, spoken_replies.set_enabled | GET /settings/{key}, get_enabled() |
| `command_history` | every /command input | api.py command path | GET /command-history, retriever, history_search tool |
| `knowledge_memory` | /remember facts (key, value) | executor memory handlers | /memory, retriever, memory_search tool, chat prompt builder |
| `chat_messages` | UI-rendered chat transcript | POST /chat | GET /chat |
| `conversation_messages` | Hermes session turns | hermes/conversation.py | retriever, /hermes chat history |
| `connectors` | connector configs (e.g. google_calendar OAuth tokens) | /connectors API | connector registry |
| `browser_profiles` | persistent Chrome profile rows for browser awareness | database/profiles.py | browser_awareness driver |

## File-backed stores

| Store | Location | Owner | Notes |
| --- | --- | --- | --- |
| Hermes task sandbox | `sandbox/tasks/<id>/` + `sandbox/index.json` | hermes/sandbox.py | agent/orchestrator/ai_chain runs; `/clean` prunes successes; also a `Backend/sandbox/` copy depending on server cwd (see DIVERGENCE.md #8) |
| ai_chain run folders | `Backend/results/ai_chain/<ts>_<slug>/` | ai_chain/storage.py | prompts/responses/images per run |
| Knowledge entities | `Backend/knowledge/*.json` | knowledge/manager.py | apps + websites |
| Skill manifests | `Backend/skills/*/manifest.json` | skills/registry.py | discovery metadata |
| ai_chain calibration | `ai_chain/calibration.json` (git-ignored) | calibrate.py | per-machine site tuning |
| Chrome profiles | `ai_chain/.chrome-profile/`, browser-awareness profile dirs | respective drivers | persistent logins |

## In-memory (process-local)

| Store | Location | Notes |
| --- | --- | --- |
| BrowserCache | `database/cache/browser_cache.py` | current page/selection from /browser endpoints; module singleton |
| EventBus history | `events/bus.py` | last 100 events, debugging only |
| Chat mode / test mode | `brain/modes.py` | resets on restart |
| Hermes orchestrator/sandbox singletons | `hermes/service.py` | lazy, per-process |

## Access rules observed in code

- All SQL goes through `DatabaseManager.execute/fetch_one/fetch_all`
  (thread-safe connections; `tests/test_api_db_threads.py`).
- Skills never open SQLite directly (project_tracker uses
  `database/manager`); knowledge JSON is only touched via KnowledgeManager.
- `Backend/scripts/check_no_db_staged.py` guards against committing the DB.
