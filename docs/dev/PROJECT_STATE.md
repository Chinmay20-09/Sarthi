# Project state

Snapshot of the repository as of **2026-09-16** (post-IPC commit `0108235`).
Facts only; plans are clearly separated. This consolidates the former
PROJECT_STATE, CAPABILITIES, DIVERGENCE, DEAD_CODE/DUPLICATION and
FORENSIC_SUMMARY documents — historical details are preserved in
`docs/archive/documentation-reset-2026-09/`.

Status labels: **IMPLEMENTED** (code + caller evidence, usually test-covered)
· **PARTIAL** · **PLANNED** (placeholder evidence only) · **CANDIDATE**
(removal candidate).

## Current architecture (one paragraph)

FastAPI backend (`Backend/api.py`, 46 endpoints) serving a tkinter desktop
client and a static web dashboard. Commands flow through a deterministic
pipeline — interpreter → pass-through planner → fuzzy resolver →
handler/skill executor — and reach Hermes in two cases: before execution when
a task-shaped sentence's only reading is a plain web search, and after a
failure when the heuristic router calls the request complex. Hermes is one
bounded loop (`hermes/agent.py`: retrieval → model → validated tool call,
default 3 iterations) behind one validator and one tool registry; it never
controls the machine directly. Eleven manifest-discovered skills provide apps,
browser, browser-awareness, project tracking, speech, scanning, personal
context, user config, conversational fallback, AI chaining, and terminal file
commands (cd/echo/create/write). LLM access is
provider-abstracted with a local Ollama default.

**Deterministic-first principle.** Sarthi (the Brain) prefers deterministic
orchestration whenever a known, validated capability path exists; Hermes is
the escalation path for complexity, not the default mechanism. Physical
execution belongs only to Hands — today the local `DesktopHand` behind
`hands/base.py`, or the `RemoteDesktopHand` over the Desktop Agent IPC when
`SARTHI_DESKTOP_AGENT_MODE=remote`. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the full canonical terminology map.

## Implemented (verified by code + passing tests)

- Deterministic command pipeline with compound command support
  ("open X and search/play Y"), slash commands, site-aware search/play
- Open/close apps and websites; unknown-app scan/browser-search fallback
- AI chaining (ChatGPT→Gemini by default; 7 sites) with dry-run planning,
  DOM-assisted locating, hands-off safety, run transcripts, sandbox records
- Browser awareness loop for arbitrary sites (Selenium/Playwright + bs4)
- Bounded Hermes agent with 11 whitelisted tools and hybrid retrieval
- Terminal capability (TERMINAL): cd/echo/create as structured hand actions
  plus `write` mapped onto the existing write_file action; cwd tracked in
  FilesystemBackend, every path scoped to the allowed roots (no shell, no
  subprocess); terminal skill (11th) + Hermes terminal tool
- Complexity router (pure heuristics) gating the fallback
- /remember memory, session history, sandbox with /clean semantics
- Project tracking over GitHub; Google Calendar connector (OAuth web + desktop)
- Voice input (faster-whisper) and voice output (SAPI TTS + spoken replies
  for every response, toggleable)
- Skill registry with enable/disable; event bus; test (dry-run) mode
- In-app test runner with hardware telemetry
- **Brain ↔ Desktop Agent IPC** (2026-09-16): `RemoteDesktopHand`,
  `DesktopAgentClient` transport, `desktop_agent.py --server`
  (`POST /execute`, `GET /health`, `GET /capabilities`); mode-selected via
  `SARTHI_DESKTOP_AGENT_MODE=local|remote` — test-locked by
  `tests/test_desktop_agent_ipc.py`

## Partially implemented

- **Multi-step planning**: `brain/planner.py` is a locked pass-through
- **AutomationEngine**: assistant registration + `assistant.json` generation
  only; the unreachable event pipeline was removed (AD-06), and a
  trigger-based lifecycle is planned (AD-14)
- **Browser extension bridge**: `/browser/action` placeholder, no extension
- **Desktop hand in production**: used by close/launch paths and the CLI;
  in remote mode actions reach the agent over IPC, but nothing in the
  product UI surfaces the remote mode yet
- **Provider/capability discovery**: Desktop capabilities are reported
  statically (`hands/desktop/capabilities.py`); no runtime
  capability→provider→Hand registry
- **Sarthi Server independence**: with the IPC transport the Brain can run
  apart from the executing machine, but there is no pairing/auth/transport
  security and Android/Browser/IoT Hands do not exist

## Known limitations

- Voice CLI and /listen require the undeclared sounddevice/faster-whisper
  stack; voice output requires Windows.
- Real AI-chain runs need one-time logins in the automation Chrome profile
  and site calibration; UI changes can degrade to the page-copy fallback
  (the coordinate scan grid is disabled unless `AI_CHAIN_COORDINATE_SCAN=1`).
- The complexity router keys part of its verdict on the first word; polite
  prefixes ("please open chrome") score as complex, but the deterministic
  pipeline handles them first, so the verdict never costs a model call.
- A long search query that mentions task verbs ("…and rename them") is
  escalated to Hermes by the task-shaped gate rather than searched literally;
  since 2026-09-16 the agent can execute terminal file steps (cd/echo/
  create/write via the TERMINAL capability and its `terminal` tool), while
  broader file operations (move/copy/delete/search) remain unavailable (AD-04,
  narrowed).
- LAN exposure (0.0.0.0 bind) has no authentication — applies to both the
  FastAPI server and the Desktop Agent IPC server (documented as a
  LAN/local development boundary in `desktop_agent.py`).
- `Backend/.env.example` documents `HERMES_AGENT_MAX_ITERATIONS=5` while the
  code default is 3 (`HermesConfig.agent_max_iterations`) — the code is the
  source of truth.
- A stray gitignored repo-root `sandbox/` (4 stale queries) exists but no
  longer receives records (AD-01 made `Backend/sandbox` canonical).

## Current architectural issues (deferred, with reasons)

These are understood, deliberately unresolved; decision reasoning is in the
archived [ARCHITECTURAL_DECISIONS.md](../archive/documentation-reset-2026-09/ARCHITECTURAL_DECISIONS.md)
(AD-01…AD-16).

| Item | Status | Why |
| --- | --- | --- |
| AI chain's own control layer duplicates `hands/desktop/input.py` | DEFERRED (AD-12) | Real runs are untested (dry-run only); re-pointing is a behaviour-risk change needing its own harness |
| Skill `handled` vs `success` failure semantics inconsistent across skills | DEFERRED (D-07) | Needs a per-skill audit, not a consolidation change |
| `sarthi.bat` vs `config.py` bind address duplication | DEFERRED (D-10) | Two sources kept in sync manually; cosmetic launcher change |
| Sandbox → Knowledge promotion lifecycle | DEFERRED (AD-13) | Needs a promotion rule + user confirmation boundary |
| Automation as a trigger-based, Sarthi-owned lifecycle | DEFERRED (AD-14) | Requires task persistence + trigger ownership decisions |
| Unified execution-observation contract (`ToolResult` vs `DesktopResult` vs `InspectionResult`/`StepOutcome`) | DEFERRED (AD-15) | Cross-cutting change; the Hermes-facing view is already normalized by `ToolResult` |
| Two browser DOM readers (browser_awareness vs ai_chain dom) | DEFERRED (AD-11) | Both working and tested; different consumers |
| IPC: no authentication/pairing/transport security on the Desktop Agent boundary | OPEN | The boundary is new (2026-09-16); documented as LAN-local only |
| Broader file operations (move/copy/delete/search/list) on the hand | OPEN (narrowed from AD-04) | cd/echo/create/write now exist (TERMINAL capability); the rest stay out of scope until individually reviewed |

## Removal candidates (kept for now)

- `ai_chain/browser_automation.py` (v1.7 DOM engine) — production-dead but
  the only place its DOM-resolver paths are tested
- `skills/automation_engine/assistants/brain_assistant/analyzer.py` —
  unreachable, but the only consumer of the assistant-response contract

## PLANNED (not implemented — placeholder evidence only)

- Android APK distribution (`apk/README.md` — reserved, empty)
- Remote Hands beyond the Desktop (Android / Browser / IoT)
- Capability/provider discovery: Hands report what they can provide;
  capability → provider → Hand routing
- Unified capability registry inside the knowledge layer
- WINDOW_CONTROL / SHELL capabilities (declared, unregistered)
- Real multi-step planning in the brain pipeline
- Broader file capability beyond cd/echo/create/write — move/copy/delete/
  search/list — so task-shaped instructions can be fully executed (AD-04
  residue)
- Authenticated/authorized IPC semantics, device pairing, transport security

## Historical forensic material

The 2026-09-13/14 forensic audit (divergence matrix, dead-code audit,
duplication report, consolidation plan/report, decision log) is preserved in
`docs/archive/documentation-reset-2026-09/`. Its still-relevant residue is
exactly the table above; everything else was either resolved, intentional, or
not reproducible.
