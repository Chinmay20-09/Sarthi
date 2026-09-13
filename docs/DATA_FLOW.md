# Data flow (observed)

The structures that actually cross component boundaries, with their real field
names.

## 1. Intent — the brain's unit of work

```
brain/intent.py :: Intent
    action: str          # "open", "search", "play", "chain", "browse", ...
    target: str          # resolved/trimmed target (app/site/query)
    site: str = ""       # site-aware search/play carrier ("open youtube and search X")
    confidence: float
    raw_text: str        # original sentence (the chain skill re-parses this)
```

Produced by the interpreter (1+ per sentence), mutated by the resolver
(`target` rewrite), consumed by the executor and every skill.

## 2. BrainResponse → API dict

```
brain/response.py :: BrainResponse.to_api_dict()
    action, target, confidence, status, success, execution_ms,
    text          # assistant bubble text
    result        # skill payload; may contain result.visual = {type, data}
    error, resolved, source, provider, model,
    steps[]       # one step_payload per executed intent (multi-query commands)
```

api.py adds `input`, `mode`, `routing` (from `_detect_response_mode`) and
wraps everything in the client envelope `_client_envelope()`:
`{success, response, data, ...legacy fields}`.

## 3. Hermes Task / ProviderResponse

```
hermes/models.py :: Task
    id, prompt, task_type ("chat"|"agent"|"test"|"ai_chain"), history, memory, instructions

hermes/providers/base.py :: ProviderResponse
    success, text, provider, model, tool_used, error, ...timing
```

Flows: agent/orchestrator → provider manager → provider adapter; saved to the
sandbox with the full trace.

## 4. Agent result dict

```
hermes/agent.py run() →
    success, text, tool_used, iterations, duration_ms, timed_out,
    route ("hermes"), reason, provider, model, trace[], error
```

api.py lifts selected fields into the `/command` response under `result` and
`hermes` keys (api.py:385-402).

## 5. Complexity Route

```
hermes/router.py :: Route
    route: "fast" | "hermes"
    reason: machine-readable ("simple_command", "compound_connector", ...)
    score: int (>=1 means complex)
    signals: list[str]
```

## 6. ai_chain structures

```
ai_chain/models.py
    ChainRequest(query, ai1, ai2, save_images)
    StepOutcome(index, site_key, site_label, prompt, response, error, duration_ms, artifacts)
    ChainOutcome(request, success, status, steps, run_dir, message)
```

`run_ai_chain` persists each run to `results/ai_chain/<timestamp>_<slug>/`
(01_query.txt, 0N_stepN_<site>_response.txt) and mirrors a trace into the
Hermes sandbox (`task_type="ai_chain"`).

## 7. Events

```
events/bus.py :: Event(name, data, source, timestamp)
```

Published: `intent_received`, `command_completed`, `voice_command_received`,
`speech_recognized` (api.py); skill/knowledge/system events defined in
`events/__init__.py`. Consumed by: voice responder (`command_completed`),
logging.

## 8. Skill result contract

Every skill returns a plain dict (no exceptions for control flow):

```
{success: bool, status: str, result: {...}, error: str|None, handled?: bool}
```

`handled: True` means "this skill owns the intent even though it failed" —
the executor stops the skill walk there (brain/executor.py:154-171).
Skills may embed `result.visual` cards (e.g. `open_choice`) that the UI
renders.

## 9. Tool call protocol (Hermes ⇄ Sarthi)

```
model output → parse_tool_call → {"tool": name, "arguments": {...}}
validate_tool_call → verdict (valid / reason / message)
ToolRegistry.execute → ToolResult(success, tool, result, error, invalid?, data)
```

Registered tools expose `name`, `description`,
`parameters` (JSON-schema subset) for the LLM prompt.

## 10. Persistence shapes

| Store | Shape |
| --- | --- |
| `sandbox/index.json` | `{query_string: [ {task_id, prompt, provider, model, status, tool_used, timestamp, duration_ms} ]}` |
| `sandbox/tasks/<id>/` | metadata.json, prompt.md, response.md, trace.json |
| `results/ai_chain/<run>/` | 01_query.txt, 0N_stepN_<site>_response.txt, harvested images |
| SQLite tables | see DATABASE.md |
| `knowledge/*.json` | applications + websites entities with aliases |
