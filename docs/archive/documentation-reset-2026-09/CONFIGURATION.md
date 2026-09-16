# Configuration (observed)

Configuration lives in three layers. Verified against
`Backend/config.py`, `Backend/hermes/config/{settings,loader}.py`,
`Backend/.env.example`, and the consuming modules.

## 1. Backend/config.py (static constants)

| Key | Value | Used by |
| --- | --- | --- |
| PROJECT_ROOT / SKILLS_DIR / KNOWLEDGE_DIR / UI_DIR | Backend paths | many |
| SAMPLE_RATE / RECORDING_DURATION / RECORDING_FILE | 16000 / 5 s / temp.wav | speech recorder |
| WHISPER_MODEL / _DEVICE / _COMPUTE_TYPE | small / cpu / int8 | speech_to_text |
| API_HOST / API_PORT | 0.0.0.0 / 8000 | api.py, sarthi.bat (kept in sync manually) |
| LOG_LEVEL / LOG_FORMAT | INFO / default fmt | utils/logger |

## 2. Hermes environment variables (hermes/config/loader.py)

Core provider:

| Var | Default | Meaning |
| --- | --- | --- |
| HERMES_PROVIDER | `local` | `local` \| `openrouter` \| `openai_compatible` \| `openai` |
| HERMES_MODEL | `openai/gpt-5` | model id for the primary provider |
| HERMES_TEMPERATURE / HERMES_TIMEOUT | 0.2 / 60.0 | generation knobs |
| HERMES_SANDBOX_PATH | `sandbox` | TaskSandbox root |
| LOCAL_HERMES_URL / _API_KEY / _MODEL / _TIMEOUT | localhost:11434 / — / hermes3:8b / 180 | Ollama fallback |
| OPENROUTER_API_KEY / _URL / _HTTP_REFERER / _X_TITLE | — | OpenRouter |
| OPENAI_API_KEY (+ per-provider keys) | — | OpenAI-compatible endpoints |

Agent loop + router (Phase 3f knobs, `.env.example` documents them):

| Var | Default | Meaning |
| --- | --- | --- |
| HERMES_AGENT_MAX_ITERATIONS | 5 | tool-requesting turns per complex task |
| HERMES_AGENT_TIMEOUT | 300 | wall-clock budget (s) |
| HERMES_ROUTER_MODE | auto | auto \| always \| off |
| HERMES_ROUTER_MIN_SCORE | 1 | heuristic score threshold |

Retrieval knobs exist in `HermesConfig` (bounded context feeding).

## 3. Feature-specific environment variables

Browser awareness (`skills/browser_awareness/driver.py`):

| Var | Meaning |
| --- | --- |
| BROWSER_AWARENESS_DRIVER | `selenium` (default) \| `playwright` |
| BROWSER_AWARENESS_HEADLESS | run without a window |
| BROWSER_AWARENESS_PROFILE_DIR | persistent profile dir override |
| BROWSER_AWARENESS_CDP_URL | attach to an existing Chrome via CDP |

ai_chain (`ai_chain/calibration.py`):

| Var | Meaning |
| --- | --- |
| AI_CHAIN_PROFILE_DIR | automation Chrome profile override |
| AI_CHAIN_AUTOMATION_PROFILE | profile switch control |
| AI_CHAIN_DOWNLOADS_DIR | where generated images are downloaded |

## 4. Settings table (runtime, user-facing)

`settings` table in sarthi.db via POST/GET `/settings`:

| Key | Set by | Meaning |
| --- | --- | --- |
| github_username | user_config skill / UI | GitHub identity for project tracking |
| voice_replies | POST /settings/voice-replies | spoken replies on/off (default on) |

## 5. Calibration files

- `ai_chain/calibration.json` — per-machine site tuning written by
  `python -m skills.automation_engine.ai_chain.calibrate` (git-ignored).
- `brain/keywords.json` — wordfinder keywords ending `open ...` targets
  (editable; `keywords.example.json` is the template).

## Loading order

`config.py` imports are plain constants. Hermes config is read per
`ConfigLoader().load()` call (env + .env via python-dotenv) — changes apply to
newly built components. The settings table is read on each access.
