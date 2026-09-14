# Automation (observed)

"Automation" means two distinct things in this repository. Both live under
`Backend/skills/automation_engine/`.

## 1. Assistant generation (the AutomationEngine core)

- **What it is**: `AutomationEngine` (`engine.py`) is an assistant registry
  (`register_assistant`, `run_assistant`); the wired assistant analyses a
  skill folder and generates an `assistant.json` config from its
  `manifest.json`.
- **Trigger**: the skill wrapper routes intents containing "generate" →
  `_handle_generate(target)` → `BrainAssistant.analyze(skill_folder)`.
- **Representation**: `manifest.json` (input) → `assistant.json` (output);
  `contracts.py` holds the assistant protocol (`ProjectState`,
  `ChangeRequest`, `AssistantResponse`).
- **State**: generated `assistant.json` files on disk.
- **Reality check**: PARTIAL. There is **no** `run(event)` lifecycle — the
  former event pipeline (`engine.run`, `events.py`, `context.py`,
  `preview.py`) was unreachable and was removed in the 2026-09-14 pass, and
  the non-functional `analyze` command was dropped. A trigger-based,
  Sarthi-owned automation lifecycle is a planned feature (AD-14).

## 2. AI chaining (laptop-controlled automation)

Delegated entirely to the `ai_chain/` package — see [CHAINING.md](CHAINING.md).
The skill wrapper routes `chain|automate` actions there (`skill.py:65-67`).

## Triggers summary

| Trigger | Path |
| --- | --- |
| `chain ... from <AI> to <AI>` / `automate ...` / `run ... from <AI> to <AI>` | interpreter `_parse_chain_intent` → chain intent → automation skill |
| `open <chatgpt/gemini/...> ... to <AI>` | interpreter `_parse_open_chain` → chain intent |
| `generate assistant for <skill>` | automation skill → BrainAssistant |

## State

| State | Where |
| --- | --- |
| Run transcripts | `Backend/results/ai_chain/<timestamp>_<slug>/` |
| Sandbox records | Hermes sandbox (`task_type="ai_chain"`) |
| Site calibration | `ai_chain/calibration.json` (git-ignored, user-generated) |
| Automation Chrome profile | `ai_chain/.chrome-profile/` (persistent logins) |
| Step handoff | `ai_chain/handoff.py` (file-backed, reset per run) |
