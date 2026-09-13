# Capability inventory (observed)

What Sarthi can currently do. "Implemented" means repository evidence supports
it (code path + caller; test coverage noted separately). Status classes:
IMPLEMENTED, PARTIAL, PLANNED, EXPERIMENTAL, UNUSED.

| Capability | Implemented | Entry Point | Main Components | Dependencies | Tested | Status |
| ---------- | ----------- | ----------- | --------------- | ------------ | ------ | ------ |
| Deterministic command pipeline (interpret→plan→resolve→execute) | Yes | `BrainEngine.process` | brain/*, knowledge/entity_resolver | rapidfuzz | test_brain_engine, test_interpreter | IMPLEMENTED |
| Open applications | Yes | "open <app>" | executor handle_open → AppLauncherSkill | psutil (scanner) | test_app_launcher, test_scanner | IMPLEMENTED |
| Open websites / site search / site play | Yes | "open X", "open X and search Y", "open X and play Z" | executor handle_open → BrowserSkill | knowledge JSON | test_browser, test_interpreter_search_split | IMPLEMENTED |
| Close applications | Yes | "close X" | executor handle_close → DesktopHand | psutil, pywin32 | test_executor, test_desktop_hand | IMPLEMENTED |
| Unknown-app fallback (scan/browser-search choice, remembered) | Yes | open_choice visual card | executor handle_open, /websites/search-and-save | knowledge | test_backend_api | IMPLEMENTED |
| AI chaining ChatGPT→Gemini (laptop RPA) | Yes | "chain/run/automate X from A to B", "open chatgpt ... to gemini" | AutomationSkill._handle_chain, ai_chain/* | pyautogui, selenium/bs4, keyboard | test_ai_chain (dry-run only) | IMPLEMENTED (real runs need logins + calibration) |
| Declarative browser chains (multi-site, DOM) | Yes (library + tests, no production caller) | `run_browser_chain` import | ai_chain/browser_automation.py | selenium, bs4 | test_browser_automation | IMPLEMENTED + UNUSED |
| Browser awareness (DOM inspection of arbitrary sites) | Yes | "open example.com and do X" → browse intent | BrowserAwarenessSkill + manager loop | selenium/playwright, bs4 | test_browser_awareness | IMPLEMENTED |
| Hermes plain chat (conversation mode + NLP fallback) | Yes | conversation mode, fallback skill | hermes.service.chat, NLP skill | provider (Ollama default) | test_local_provider, test_nlp_skill, test_chat_modes | IMPLEMENTED |
| Complexity router (fast/complex gate) | Yes | api.py fallback | hermes/router.py, service.route_command | none (pure heuristics) | test_hermes_router, test_hermes_pipeline_integration | IMPLEMENTED |
| Bounded agent loop with tools | Yes | api.py fallback → run_task | hermes/agent.py, validator, tool_registry | provider | test_hermes_agent, test_hermes_validator | IMPLEMENTED |
| Hybrid retrieval (memory/history/sandbox/knowledge) | Yes | agent step 2 | hermes/retriever.py | SQLite, sandbox | test_hermes_retriever, test_sandbox_query_index | IMPLEMENTED |
| Hermes tools (open app/website, close, search web, browser_ask, history/memory/project/github/personal context) | Yes | agent loop | hermes/tools/* (10 tools) | delegate to skills/connectors | test_hermes_tools | IMPLEMENTED |
| Long-term memory (/remember /recall /forget) | Yes | slash commands | brain/executor memory handlers, knowledge/memory | SQLite | test_chat_memory_api | IMPLEMENTED |
| Conversation history (session store, chat UI persistence) | Yes | /hermes/chat, /chat | hermes/conversation.py, api /chat endpoints | SQLite | test_conversation_history, test_chat_memory_api | IMPLEMENTED |
| Project tracker (GitHub-backed projects + prompts) | Yes | project_tracker skill, /projects API | skills/project_tracker/* | httpx, GitHub API | test_project_tracker, test_projects_api | IMPLEMENTED |
| Google Calendar connector | Yes | /connectors endpoints | connectors/google_calendar/* | google-auth-oauthlib | test_connectors | IMPLEMENTED (single connector) |
| Voice input (record + whisper STT) | Yes | POST /listen, main.py CLI | speech/, skills/speech | sounddevice, faster-whisper | test_recorder, test_stt | IMPLEMENTED |
| Voice output (TTS announcements + spoken replies) | Yes | event bus, automation | utils/voice, utils/spoken_replies | pywin32 SAPI / PowerShell | test_spoken_replies | IMPLEMENTED |
| Desktop hand capability layer (standalone agent) | Partial | desktop_agent.py CLI | hands/desktop/* | psutil/pyautogui/etc | test_desktop_hand | IMPLEMENTED + PARTIALLY USED (no IPC; only `close` handler in production path) |
| Browser extension bridge (/browser/* endpoints, page/selection cache) | Partial | /browser routes | skills/browser/routes+service, database/cache | — | none | PARTIAL (action endpoint is a placeholder; no extension in repo) |
| In-app test runner (60 prompts + telemetry dashboard) | Yes | POST /test/run, GET /test/prompts | api.py test runner, utils/telemetry, reading.py | psutil | untested endpoint | IMPLEMENTED |
| Test (dry-run) mode | Yes | POST /test-mode, get_test_mode() | brain/modes, skills honour it | — | test_chat_modes | IMPLEMENTED |
| Skill registry (manifest discovery, enable/disable) | Yes | /skills API, engine startup | skills/registry.py | manifest.json files | test_skill_base, test_backend_api | IMPLEMENTED |
| Event bus | Yes | imports | events/bus.py | — | test_backend_api (indirect) | IMPLEMENTED |
| Automation assistant generation (BrainAssistant → assistant.json) | Partial | "generate assistant for <skill>" | automation_engine engine + assistants | manifest analysis | test_brain_assistant (smoke) | PARTIAL (analyze is a stub returning empty capabilities) |
| Multi-step planner (real decomposition) | No | — | brain/planner.py pass-through | — | test_planner (locks pass-through) | PLANNED |
| Flutter client | No | — | flutter/README only | — | — | PLANNED |
| Android APK | No | — | apk/README only | — | — | PLANNED |
| Brain↔Desktop agent IPC | No | — | desktop_agent.py docstring only | — | — | PLANNED |

Counts: 24 implemented, 3 partial, 3 planned, 1 implemented+unused library.
