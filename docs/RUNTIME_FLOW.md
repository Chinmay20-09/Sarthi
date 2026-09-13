# Runtime flow (observed)

Step-by-step trace of the two real execution paths. Line references verified
against the working tree.

## Path 1 — deterministic (fast) path

Input: `POST /command {"query": "open youtube and search lofi"}`

1. **Envelope & empty check** — `api.py:_process_command_text` (line 317).
   Empty input returns the "Please enter a command." envelope.
2. **Event** — `bus.publish("intent_received", ...)` (api.py:339).
3. **Mode commands** — `detect_mode_command(text)`; "conversation mode" /
   "/exit" switch modes and return immediately (api.py:342-350).
4. **Conversation mode short-circuit** — when conversation mode is active the
   brain pipeline is never invoked; the text goes to `hermes.service.chat`
   (plain LLM chat, no tools) via `_conversation_response` (api.py:353-360).
5. **BrainEngine.process** — `brain/engine.py:129`:
   - `split_queries` splits on `.` while protecting domain tokens
     (`brain/interpreter.py:185`).
   - each sentence → `_interpret_query`:
     - slash commands map 1:1 to actions (`/remember x` → `remember`)
     - AI-chain shapes (`run X from chatgpt to gemini`,
       `open chatgpt ... to gemini`) → single `chain` intent
     - `open X and search/play Y` → two intents (open + site-aware search/play)
     - bare unknown domain + task → `browse` intent (browser awareness)
     - otherwise → single intent with keyword-trimmed target
   - Planner passes each intent through unchanged (`brain/planner.py:36`).
   - Resolver fuzzy-matches `intent.target` against the knowledge store
     (`knowledge/entity_resolver.py`), sets `context.resolved`.
   - Executor dispatches each intent **in order, fail-fast**
     (`engine._execute_plan`):
     1. built-in handler if the action has one (open/close/browse/remember/
        recall/forget/clean — `brain/executor.py:271-369`)
     2. default handler (none registered by default)
     3. every registered skill in turn; first success wins; a skill with
        `handled=True` owns the failure (executor.py:154-171). The NLP
        fallback skill is sorted LAST (`engine._load_skills`).
6. **Response** — `BrainResponse.to_api_dict()` plus `input`, `mode`,
   `routing` (from `_detect_response_mode`, api.py:237).
7. **Event** — `bus.publish("command_completed", result)` → the voice
   responder speaks the reply aloud when enabled (`utils/spoken_replies.py`,
   subscribed at api.py import time).

## Path 2 — complex (Hermes) fallback

Reached only when Path 1 returns `success: false` **or** `routing == "hermes"`
(`api.py:374-377`).

1. **Complexity router** — `hermes.service.route_command(text)`:
   - pure text heuristics (`hermes/router.py`): first word action credit,
     compound connectors, dataflow verbs, research nouns, AI interaction,
     deixis, multiple questions, follow-up clauses, long-command penalty,
     deterministic AI-chain veto.
   - config knobs: `HERMES_ROUTER_MODE` (auto/always/off) and
     `HERMES_ROUTER_MIN_SCORE` (`hermes/service.py:112-133`).
2. When the route is `hermes`: **HermesAgent.run** (`hermes/agent.py:99`):
   1. deterministic fast path again (cheap safety net; NLP-source results are
      deliberately NOT short-circuited — agent.py:135-140)
   2. hybrid retrieval — `hermes/retriever.py` pulls bounded context from
      knowledge_memory, command_history, settings, knowledge entities, the
      sandbox query index and session history. No vector DB; SQL + fuzzy.
   3. bounded loop (`_loop`): build instructions from the query + registered
      tool list → model call via the provider manager (primary + local
      fallback) → `parse_tool_call`; a plain answer ends the loop; otherwise
      `validate_tool_call` (Phase 3c gate) → refusal fed back once →
      `ToolRegistry.execute` → follow-up instructions. Caps:
      `HERMES_AGENT_MAX_ITERATIONS` (default 5) and `HERMES_AGENT_TIMEOUT`
      (default 300 s).
3. **Sandbox persistence** — every agent run is saved to
   `sandbox/tasks/<task_id>/` and indexed by query in `sandbox/index.json`
   (`agent._persist`). Failed runs are kept by `/clean`.
4. On agent failure the original (failed) pipeline result is returned
   unchanged (`api.py:404` catch keeps `result`).

## Voice path (input)

`POST /listen` (api.py:449) → SpeechSkill (lazy) → `sounddevice` recording →
`faster-whisper` transcription → same mode checks and brain pipeline as text.
The pipeline's own output is tagged `routing == "speech"` so the voice
responder never double-speaks it.

## Automation path (ai_chain)

Commands matching `chain|automate` intents or the deterministic AI-chain shape
dispatch to `AutomationSkill._handle_chain` (`skills/automation_engine/skill.py:76`)
→ `run_ai_chain` (`ai_chain/chain.py:64`): hands-off warning + countdown →
drive AI1 site → hand off AI1's reply via `ai_chain/handoff.py` → drive AI2 →
save every prompt/response to `results/ai_chain/<run>/` and the Hermes
sandbox. Details in [CHAINING.md](CHAINING.md).
