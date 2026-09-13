# Automation (observed)

"Automation" means two distinct things in this repository. Both live under
`Backend/skills/automation_engine/`.

## 1. Assistant generation (the AutomationEngine core)

- **What it is**: `AutomationEngine` (`engine.py`) coordinates *assistants*
  that analyse a skill folder and generate an `assistant.json` config from its
  `manifest.json`.
- **Trigger**: the skill wrapper (`skill.py:70-78`) routes intents containing
  "generate" → `_handle_generate(target)` → `BrainAssistant.analyze(skill_folder)`.
- **Representation**: `manifest.json` (input) → `assistant.json` (output).
  Supporting modules: `context.py` (ProjectScanner), `contracts.py`
  (AssistantResponse), `events.py` (AutomationEvent), `preview.py`
  (PreviewGenerator).
- **State**: generated `assistant.json` files on disk.
- **Reality check**: the engine's `run(event)` path exists but the only
  wired assistant is BrainAssistant (analysis); the `analyze` command returns
  a stub with empty capabilities (`skill.py:171-180`). PARTIAL.

## 2. AI chaining (laptop-controlled automation)

Delegated entirely to the `ai_chain/` package — see [CHAINING.md](CHAINING.md).
The skill wrapper routes `chain|automate` actions there (`skill.py:65-67`).

## Triggers summary

| Trigger | Path |
| --- | --- |
| `chain ... from <AI> to <AI>` / `automate ...` / `run ... from <AI> to <AI>` | interpreter `_parse_chain_intent` → chain intent → automation skill |
| `open <chatgpt/gemini/...> ... to <AI>` | interpreter `_parse_open_chain` → chain intent |
| `generate assistant for <skill>` | automation skill → BrainAssistant |
| `analyze <skill>` | automation skill → stub |

## State

| State | Where |
| --- | --- |
| Run transcripts | `Backend/results/ai_chain/<timestamp>_<slug>/` |
| Sandbox records | Hermes sandbox (`task_type="ai_chain"`) |
| Site calibration | `ai_chain/calibration.json` (git-ignored, user-generated) |
| Automation Chrome profile | `ai_chain/.chrome-profile/` (persistent logins) |
| Step handoff | `ai_chain/handoff.py` (file-backed, reset per run) |
