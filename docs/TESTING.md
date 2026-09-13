# Testing (observed)

## Suite facts (verified by running it)

- **52 test files** in `tests/`, **1021 tests collected and run**.
- **Full-suite result at documentation time: `1021 passed`** in ~252 s
  (`pytest`, pyproject: testpaths=tests, addopts=-q).
- pythonpath bootstraps `Backend/` and `Desktop/client/` so flat imports work.

## What is actually tested (evidence)

| Area | Files | Depth |
| --- | --- | --- |
| Brain pipeline | test_brain_engine, test_interpreter, test_interpreter_search_split, test_planner, test_executor, test_wordfinder, test_normalizer-behaviour via test_resolve/test_resolver_matching/test_fuzzy | unit + integration (real pipeline, fake skills) |
| API contract | test_backend_api, test_chat_modes, test_chat_memory_api, test_projects_api, test_connectors, test_api_db_threads | real FastAPI TestClient |
| Hermes agent loop | test_hermes_agent, test_hermes_validator, test_hermes_tools, test_hermes_router, test_hermes_retriever, test_sandbox_query_index, test_conversation_history | fake providers (no network) |
| Provider abstraction | test_provider_abstraction, test_local_provider, test_fallback, test_fallback_integration | fake/queued providers |
| Pipeline boundaries | test_hermes_pipeline_integration, test_pipeline_compatibility, test_architecture_boundaries | locks routing + client/backend import rules |
| ai_chain | test_ai_chain (dry-run plan path), test_browser_automation (DOM resolver) | no real browser/mouse in tests |
| Browser awareness | test_browser_awareness | manager loop with injected fakes |
| Desktop hand | test_desktop_hand | validation gate + fake actions |
| Knowledge | test_knowledge_manager, test_scanner | unit |
| Skills | test_skill_base, test_app_launcher, test_browser, test_project_tracker, test_personal_context, test_nlp_skill, test_brain_assistant | unit/dispatch |
| Client | test_desktop_client | controller/backend parsing without display/network |
| Voice replies | test_spoken_replies | mocked announce |
| Infra | test_database_manager, test_database_optimizations, test_telemetry, test_recorder, test_stt, test_phrase_generator | unit |

## What is NOT tested (evidence-based)

- **Real laptop automation**: every ai_chain test runs in dry-run/plan mode.
  Real mouse/keyboard runs (PyAutoGUI, hotkey abort, login handling) are
  untested by design; real-run evidence exists only in
  `Backend/results/ai_chain/` and sandbox records.
- **Real LLM providers**: all model calls are faked; no integration test
  against Ollama/OpenRouter.
- **Real browsers**: Selenium/Playwright are never started by the suite.
- **`POST /test/run` and `/system/metrics` endpoints**: untested (they shell
  out to hardware telemetry).
- **`main.py` / `main-test.py` / `desktop_agent.py` CLIs**: no CLI tests.
- **`hermes/main.py`** standalone loop: untested.
- **`/browser/*` endpoints**: no dedicated tests (service is a placeholder).
- **Voice output on real hardware**: spoken_replies tests mock `announce`.

## Test style notes

- Integration tests use the real app/pipeline with fakes at the network and
  hardware boundary — the suite runs headless and offline.
- `tests/test_architecture_boundaries.py` locks package-layer rules (e.g.
  the Desktop client must not import backend internals).
- The in-app runner (`POST /test/run`, 60 prompts in `test_prompts.json`) is
  a separate, telemetry-flavoured smoke harness — not part of pytest.
