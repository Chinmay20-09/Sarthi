# Testing

How to run Sarthi's tests and what they do and do not cover.

## How to run tests

```bash
pytest                       # full suite from the repository root
pytest tests/test_brain_engine.py        # one file
pytest tests/test_hermes_agent.py -k routing   # subset by keyword
SARTHI_TEST_VOICE=0 pytest   # silence the per-file voice announcements
```

`pyproject.toml` sets `testpaths = ["tests"]` and `pythonpath =
["Backend", "Desktop/client"]`, so flat imports (`brain`, `hermes`,
`sarthi_client`) work from the repo root.

**Voice feedback:** `tests/conftest.py` announces "test_<file>.py passed"
aloud at the end of every pytest file (Windows SAPI via pywin32, PowerShell
System.Speech fallback, log line elsewhere) using `utils/voice.announce()`.
Files with failures announce their failure count. One announcement per file —
not per test. `SARTHI_TEST_VOICE=0` silences it; CI is silent by default.

## Suite facts (verified 2026-09-16)

- **56 `test_*.py` files** in `tests/`, of which **50 are pytest-collected**
  (1172 tests). The other six (test_fuzzy, test_interpreter, test_browser,
  test_brain_assistant, test_phrase_generator, test_project_tracker) are
  manual smoke scripts with top-level code and no collected tests — running
  them by hand executes their module body.
- **Full-suite result on 2026-09-16: `1172 passed`** in ~9.9 min
  (earlier baselines: 1127 before the terminal capability sprint;
  1059 after the 2026-09-14 consolidation; 1021 before it).
- Integration tests use the real app/pipeline with fakes at the network and
  hardware boundary — the suite runs headless and offline.
- `tests/test_consolidation_routing.py` is the characterization suite for the
  consolidation boundaries: routing (simple vs complex), chain-intent
  collision (both directions), the task-shaped escalation gate, the
  single-Hermes-loop invariants, sandbox root resolution from both launch
  directories, and browser semantic targeting (no real browser started).
- `tests/test_brain_hand_boundary.py` locks the Hand contract, the
  `hands/` import lock and the single-hand/single-loop invariants.
- `tests/test_desktop_agent_ipc.py` locks the IPC transport: serialization,
  request handling, transport-failure shaping, `RemoteDesktopHand` contract
  conformance, and the "no OS primitives in the remote hand" rule.

## What is actually tested

| Area | Files | Depth |
| --- | --- | --- |
| Brain pipeline | test_brain_engine, test_interpreter, test_interpreter_search_split, test_planner, test_executor, test_wordfinder, test_resolve / test_resolver_matching / test_fuzzy | unit + integration (real pipeline, fake skills) |
| API contract | test_backend_api, test_chat_modes, test_chat_memory_api, test_projects_api, test_connectors, test_api_db_threads | real FastAPI TestClient |
| Hermes agent loop | test_hermes_agent, test_hermes_validator, test_hermes_tools, test_hermes_router, test_hermes_retriever, test_sandbox_query_index, test_conversation_history | fake providers (no network) |
| Provider abstraction | test_provider_abstraction, test_local_provider, test_fallback, test_fallback_integration | fake/queued providers |
| Pipeline boundaries | test_hermes_pipeline_integration, test_pipeline_compatibility, test_architecture_boundaries, test_consolidation_routing | locks routing + escalation + client/backend import rules |
| Hands / Brain-Hand boundary / IPC | test_desktop_hand, test_brain_hand_boundary, test_desktop_agent_ipc | validation gate + fake actions + fake transport |
| Terminal capability | test_terminal_capability | capability registration, scoped filesystem cwd ops (cd/echo/create), hand dispatch, terminal skill + Hermes tool bridge, end-to-end cd→create→write→echo, traversal/scope refusals, no-subprocess scan, test-mode dry-run |
| ai_chain | test_ai_chain (dry-run plan path), test_browser_automation (DOM resolver) | no real browser/mouse in tests |
| Browser awareness | test_browser_awareness | manager loop with injected fakes |
| Knowledge | test_knowledge_manager, test_scanner | unit |
| Skills | test_skill_base, test_app_launcher, test_browser, test_project_tracker, test_personal_context, test_nlp_skill | unit/dispatch |
| Client | test_desktop_client | controller/backend parsing without display/network |
| Voice replies | test_spoken_replies | mocked announce |
| Infra | test_database_manager, test_database_optimizations, test_telemetry, test_recorder, test_stt | unit |

## What is NOT covered by automated tests

- **Real laptop automation**: every ai_chain test runs in dry-run/plan mode.
  Real mouse/keyboard runs (PyAutoGUI, hotkey abort, login handling) are
  untested by design; real-run evidence exists only in
  `Backend/results/ai_chain/` and sandbox records.
- **Real LLM providers**: all model calls are faked; no integration test
  against Ollama/OpenRouter.
- **Real browsers**: Selenium/Playwright are never started by the suite.
- **Real IPC over the network**: `test_desktop_agent_ipc.py` binds a real
  local socket in places but the transport is exercised in-process; a real
  Brain-on-machine-A → Agent-on-machine-B run is untested.
- **`POST /test/run` and `/system/metrics` endpoints**: untested (they shell
  out to hardware telemetry).
- **`main.py` / `main-test.py` / `desktop_agent.py` CLI modes / `hermes/main.py`**:
  no CLI tests (the IPC *server* logic is tested; the CLI flags are not).
- **`/browser/*` endpoints**: no dedicated tests (the service is a placeholder).
- **Voice output on real hardware**: spoken_replies tests mock `announce`.

## Manual validation requirements

Before trusting a change to these areas, validate by hand:

1. **Real AI-chain run** — `chain <query> from chatgpt to gemini` on a
   machine with logged-in sessions in the automation Chrome profile
   (`ai_chain/.chrome-profile/`) and calibrated sites
   (`python -m skills.automation_engine.ai_chain.calibrate`). Confirm the
   hands-off countdown, the Ctrl+Alt+X abort, and the run transcript in
   `Backend/results/ai_chain/`.
2. **Real browser awareness** — `open example.com and find the pricing page`
   with the `browser` extra installed; confirm the isolated Chrome session
   and the inspection loop; check persistent-profile logins separately.
3. **Real model path** — with Ollama running, issue a complex task and
   confirm the Hermes loop reasons, requests a tool, and answers; check the
   sandbox record in `Backend/sandbox/tasks/`.
4. **Remote desktop mode** — start `python Backend/desktop_agent.py --server`
   on the target machine, set `SARTHI_DESKTOP_AGENT_MODE=remote` +
   `SARTHI_DESKTOP_AGENT_HOST/PORT` on the Brain side, then `close <app>`
   and confirm the process dies on the agent's machine. Verify the agent's
   structured failure when it is unreachable.
5. **Voice hardware** — `POST /listen` with a real microphone and confirm
   transcription; confirm spoken replies with TTS enabled
   (`/settings/voice-replies`).

## In-app test runner (not pytest)

`POST /test/run` runs the 60 prompts in `Backend/test_prompts.json` through
BrainEngine in test (dry-run) mode with hardware telemetry; `POST /test-mode`
toggles the dry-run mode. It is a smoke/telemetry harness — a separate
mechanism from the pytest suite.
