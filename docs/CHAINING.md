# Chaining (observed)

AI chaining = send the user's query to one AI website, then feed its reply to
a second AI website, hands-off. Everything lives in
`Backend/skills/automation_engine/ai_chain/`.

## Chain representation

- **Chain request**: `ChainRequest(query, ai1, ai2, save_images)` parsed by
  `ai_chain/parsing.py::parse_chain_command` from forms:
  - `chain <query> from <AI1> to <AI2>` (explicit)
  - `run|automate <query> from <AI1> to <AI2>`
  - `open <AI1> and <query> ... to <AI2>` (open-flavour)
  - no from/to → defaults `chatgpt → gemini`
- **Steps**: always 2 (AI1 → AI2). There is no N-step production chain runner;
  the declarative N-step library exists but has no caller (see DEAD_CODE.md).
- **Supported sites** (`ai_chain/calibration.py::DEFAULT_SITES`): chatgpt,
  gemini, claude, perplexity, grok, deepseek, copilot (+ aliases in
  `SITE_ALIASES`, mirrored in `brain/interpreter.py::_CHAIN_AI_NAMES`).

## Execution flow (`ai_chain/chain.py::run_ai_chain`)

1. `resolve_site` both AIs (unknown → failed outcome, saved to sandbox).
2. `execute=None` defers to test mode: dry-run `_plan_only` (no machine
   control) — this is what unit tests and `POST /test/run` exercise.
3. Real run: HANDS-OFF banner + 5 s countdown + TTS announcement;
   abort via Ctrl+Alt+X hotkey or mouse-corner failsafe (`control.py`).
4. Step 1: `WebAiDriver.ask(spec1, query)` — open site, paste prompt, wait for
   reply, Ctrl+A/Ctrl+C capture, `extract_reply` pulls the answer from the
   transcript (`parsing.py`), saved to `0N_stepN_<site>_response.txt`.
5. Handoff: the prompt for AI2 is the **saved backend copy** of AI1's reply
   (`handoff.load("step1_response")`), not the clipboard (chain.py:145-147).
6. Step 2: same driver against AI2.
7. Optional: image download when AI2 is image-capable (gemini/grok/copilot).
8. `_finish_and_record` → outcome + sandbox record (success and failure both).

## How output moves between steps

`ai_chain/handoff.py` — file-backed key/value store, reset at chain start
(`handoff.reset()`), keys `stepN_prompt` / `stepN_response`. The physical
clipboard is treated as scratch space that verification copies overwrite.

## Failure handling

| Failure | Behaviour |
| --- | --- |
| Unknown site name | immediate failed outcome (message from resolve_site) |
| AI1 step fails (incl. PyAutoGUI failsafe / abort) | failed outcome, error recorded, sandbox saved |
| AI2 step fails | failed outcome, step-1 artifacts kept |
| Empty AI reply | `outcome.error = "AI returned an empty reply"` |
| Login screen detected | login_markers in SiteSpec → driver reports; user must log in once in the automation profile |
| No reply found in transcript | `needs_awareness` → AwarenessExtractor asks the local Hermes model to make sense of the page text (`sites.py:176`, `awareness.py`) |
| User abort | aborted outcome + TTS "Automation cancelled" |

## Where the chain engine is invoked

| Caller | Path |
| --- | --- |
| Brain pipeline | chain intent → executor skill walk → `AutomationSkill._handle_chain` |
| (no other production caller) | `run_ai_chain` is importable (`ai_chain/__init__.py`) but only the skill invokes it |

## State & artifacts

- Run folders: `Backend/results/ai_chain/<timestamp>_<query-slug>/`
- Persistent Chrome profile with remembered logins: `ai_chain/.chrome-profile/`
- Calibration overrides: `ai_chain/calibration.json` via
  `python -m skills.automation_engine.ai_chain.calibrate`
- Sandbox: `task_type="ai_chain"`, trace = per-step {site, prompt, response,
  error, duration_ms}

## DOM assist (v1.5–v1.7)

Before clicking, `ai_chain/dom.py` (+ `selenium_dom.py` primary, Playwright
fallback) attaches read-only to the automation Chrome, parses page HTML with
BeautifulSoup, locates the affordance (composer/copy/download button), and
converts its bounding box to a window-fraction point for the controller.
If attachment or lookup fails, the driver falls back to the v1.0
estimate + scan-grid + full-page copy. See BROWSER_AUTOMATION.md.
