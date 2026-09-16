# Skills (observed)

A Skill is a capability-oriented subsystem that groups related behaviour
(app launching, browser control, speech, scanning, …). Only the skills below
exist in the repository — no others are implied.

Discovery: `skills/registry.py` scans `Backend/skills/*/manifest.json`,
instantiates `skills/<id>/main.py` (must export a `BaseSkill` subclass).
`BrainEngine._load_skills` registers every instance with the executor,
sorting fallback skills LAST (`fallback=True` attribute → NLP skill).

Verified live: `registry.discover()` + `get_all_instances()` yields exactly
these 10 skills, all enabled.

| # | Skill (id) | Version | Manifest | Entry | What it does | Called by | Tests |
| - | ---------- | ------- | -------- | ----- | ------------ | --------- | ----- |
| 1 | app_launcher | 1.2.0 | ✓ | `skills/app_launcher/main.py` | Launch desktop applications; favourites gate; needs_decision cards | executor open handler; Hermes OpenAppTool | test_app_launcher |
| 2 | automation_engine | 1.1.0 | ✓ | `skills/automation_engine/main.py` → skill.py | (a) chain intents → ai_chain; (b) "generate assistant" → BrainAssistant | executor skill walk (chain/automate/generate actions) | test_ai_chain, test_brain_assistant |
| 3 | browser | 1.1.0 | ✓ | `skills/browser/main.py` | Open/search/play websites via Knowledge Layer + webbrowser | executor open handler; Hermes OpenWebsiteTool, SearchWebTool | test_browser |
| 4 | browser_awareness | 1.0.0 | ✓ | `skills/browser_awareness/main.py` | DOM-level inspection + action loop on arbitrary sites; announces progress | executor browse handler; Hermes BrowserAskTool | test_browser_awareness |
| 5 | natural_language_processor | 1.1.0 | ✓ | `skills/natural_language_processor/main.py` | Conversational fallback via `hermes.service.chat`; `fallback = True` (registered last) | executor skill walk (last resort) | test_nlp_skill, test_fallback* |
| 6 | personal_context | 1.0.0 | ✓ | `skills/personal_context/main.py` | User's personal context fields; feeds Hermes PersonalContextTool | Hermes tool; skill walk | test_personal_context |
| 7 | project_tracker | 1.1.0 | ✓ | `skills/project_tracker/main.py` | GitHub-backed project tracking (check/status/sync/show/pending/how) + prompts | executor skill walk; /projects API shares the same DB tables | test_project_tracker |
| 8 | scanner | 1.1.0 | ✓ | `skills/scanner/main.py` | Scan installed applications into the knowledge base (scan/refresh/discover) | executor skill walk | test_scanner |
| 9 | speech | 1.1.0 | ✓ | `skills/speech/main.py` | Record + transcribe voice (`listen` action) for POST /listen | api.py /listen | test_recorder, test_stt |
| 10 | user_config | 1.1.0 | ✓ | `skills/user_config/main.py` | Set/configure actions (e.g. github_username) | executor skill walk | test_skill_base (base) |

Notes:

- There is no `manifest.json`-less skill; every skill folder is discoverable.
- Skill inputs are always `Intent`; outputs always the plain result dict
  (see DATA_FLOW.md §8).
- `automation_engine` internally registers a BrainAssistant instance in its
  constructor (`skill.py:33-35`).
- Enable/disable is runtime state via `/skills/{id}/enable|disable`
  (registry + api.py:781-798).
