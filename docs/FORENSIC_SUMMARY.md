# Forensic summary

Final report of the 2026-09-13 documentation reset. Method: repository-wide
inspection (source, configs, manifests, tests, runtime data), execution-path
tracing of the two command paths, live registry/sandbox/schema dumps, and a
full pytest run.

## Repository snapshot

- **Files inspected**: all Python under `Backend/` (brain, hermes, skills,
  hands, knowledge, connectors, database, events, speech, utils, scripts),
  Desktop client, tests, pyproject, .env.example, UI pages, sandbox/runtime
  data
- **Major subsystems**: brain pipeline, hermes LLM layer, skills (10), hands
  (desktop execution), knowledge layer, connectors, speech, events, database,
  sandbox, automation engine (ai_chain), UI (dashboard + desktop client)
- **Entry points**: FastAPI server (sarthi.bat / api.py), tkinter client
  (run.py / sarthi.exe), voice CLI (main.py), desktop agent CLI,
  hermes standalone, calibrate + clean_sandbox scripts

## Current architecture (short)

Deterministic-first two-path design: a regex/keyword pipeline handles
commands; failures fall through a heuristic complexity router to a bounded
LLM agent with 10 whitelisted tools. Skills are manifest-discovered and
registered as executor fallbacks. See ARCHITECTURE.md.

## Capability counts

| Class | Count |
| ----- | ----- |
| Implemented | 24 |
| Partial | 3 |
| Implemented + unused (library) | 1 |
| Planned | 3 |
| Experimental | 0 |

## Skill count: **10** (all registered, enabled; verified live)

app_launcher, automation_engine, browser, browser_awareness,
natural_language_processor, personal_context, project_tracker, scanner,
speech, user_config

## Tool count: **10** (Sarthi Tool Bridge)

open_app, open_website, close_app, search_web, browser_ask, history_search,
memory_search, project_get, github, personal_context

## Agent count: **4**

HermesAgent, HermesOrchestrator+ToolPlanner, BrainAssistant, Browser
Awareness manager loop

## Duplicate systems: **8** (see DUPLICATION.md)

1. Two model-driven tool loops (HermesAgent vs Orchestrator/ToolPlanner)
2. Two browser DOM stacks (browser_awareness vs ai_chain dom)
3. Two "open a website" paths (default browser vs isolated Chrome)
4. Two conversation tables (chat_messages vs conversation_messages)
5. Two live sandbox roots (cwd-relative path)
6. Two API bind-address config sources
7. Two test harnesses (pytest vs in-app runner)
8. Two GitHub data paths (project_tracker vs hermes github tool)

## Dead/orphaned systems: **9** (see DEAD_CODE.md)

1. ai_chain browser_automation.py v1.7 engine (production-dead, test-alive) — HIGH
2. pystray dependency (no imports) — HIGH
3. AutomationEngine.run(event) pipeline — MEDIUM
4. automation skill `analyze` stub — HIGH
5. /browser/action placeholder endpoint — HIGH
6. main-test.py — LOW (manual tool)
7. hermes/main.py — LOW (manual tool)
8. Backend/sandbox duplicate store — MEDIUM
9. _DETERMINISTIC_DOMAINS coverage nuance — LOW

## Architectural divergence: **12** (see DIVERGENCE.md)

D-01..D-12 as itemized there.

## Top 10 issues requiring human architectural decisions

1. **D-03 Chain default misfire (HIGH)** — AI-mentioning browser tasks
   ("Open Google, search for OpenAI, copy the URL...") execute as ChatGPT→
   Gemini chains with default AIs. Sandbox-proven. Needs an intent
   arbitration rule.
2. **D-01 Two tool loops (HIGH)** — HermesAgent and Orchestrator/ToolPlanner
   both production-wired with different caps and validation. Pick one or
   define their split explicitly.
3. **D-06 Sandbox root ambiguity (HIGH)** — cwd-relative sandbox path yields
   two task stores. Make it absolute/app-rooted.
4. **D-04 Chain regex breadth (MEDIUM)** — `open <AI> ... to <AI>` /
   `from <AI> to <AI>` regexes can capture ordinary sentences.
5. **D-05 Dual conversation tables (MEDIUM)** — define which is canonical or
   merge.
6. **D-07 Skill `handled` semantics (MEDIUM)** — inconsistent failure
   ownership across skills changes which fallback fires.
7. **D-02 Router verdict semantics (MEDIUM)** — router reasons/score can
   mislead; verdict is advisory while presented as decisive.
8. **Dup #8 GitHub paths (MEDIUM)** — hermes github tool vs project_tracker
   client re-implement the same fetch.
9. **Dead #1 v1.7 chain engine (decision)** — production-dead but
   well-tested library: promote, or remove at next cleanup.
10. **Undeclared speech deps (build)** — sounddevice/faster-whisper are
    required for advertised features but absent from pyproject; also pystray
    declared but unimported.

## Unknowns (could not be determined from repository evidence)

- Whether the `/browser/page` `/selection` endpoints have an external
  consumer (a browser extension not in this repo).
- Whether `pystray` is reserved for an unreleased tray feature.
- Which of the two sandbox roots is intended as canonical at runtime.
- Whether `main.py` voice CLI is still part of the intended user surface or
  a legacy artifact.
- Whether `AutomationEngine.run(event)` scaffolding has a designed future
  (comments suggest "later this becomes automatic discovery").
- Real-world reliability of AI-chain runs behind logins/captchas (only
  sandbox artifacts, not tests, bear witness).

## Verification performed during this reset

- `pytest` full suite: **1021 passed**, 1 warning, ~252 s.
- Live `SkillRegistry.discover()` run: 10 skills listed.
- Live SQLite dump: 10 tables enumerated.
- Sandbox/index.json parsed: chain-default misfire confirmed (task_afec33).
- All endpoint lists grepped from decorators; all dependency claims grepped
  from imports.
