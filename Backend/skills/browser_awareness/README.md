# Browser Awareness

A Sarthi capability for websites the deterministic skills cannot drive.
It does **not** replace the Brain/Executor pipeline — it extends it.

```
User
 └▶ Brain
     ├── known deterministic flow ("open youtube and play song")  → fast, unchanged
     └── arbitrary website with a task ("open example.com and find the pricing page")
         └▶ Browser Awareness
             ├── opens the site in a temporary, isolated Chrome session
             ├── inspects the DOM into a compact page snapshot
             ├── Hermes OBSERVES the snapshot (never controls the browser)
             ├── strict JSON validation against the page
             ├── Brain-validated action → safe executor
             ├── page changed → reinspect → loop
             └── temporary context destroyed when the task ends
```

Hermes answers *"what is on this page and what single action should the
Brain take next?"* and returns structured JSON. It can only reference
elements that actually exist on the page and can only request actions
from the allow-list (`navigate | click | type | select | check |
uncheck | submit | scroll`). No raw JavaScript, no shell, no arbitrary
selectors — the executor only ever uses selectors the inspector itself
generated.

## Triggers

Both forms route into the capability:

```
/browse example.com and find the pricing page
open example.com and find the More Information link
browse https://example.com/pricing compare the plans
```

**The fast deterministic path is preserved.** Known sites keep their
existing behaviour and never touch browser awareness:

```
open youtube and play motivation video   → opens youtube.com search & plays the first result (fast, unchanged)
open chatgpt and … sendit to gemini      → AI chain (unchanged)
open github.com and …                    → deterministic, unchanged
```

Only domain/URL-shaped targets that are **not** covered by the
deterministic skills ("example.com", "myshop.io/contact", ...) route to
Browser Awareness.

## Browser window & tabs

Two stacks, one interface — **Selenium is primary**, Playwright the
fallback (`BROWSER_AWARENESS_DRIVER=selenium|playwright` pins one;
unset auto-selects Selenium when installed, Playwright otherwise).
Selenium fetches its chromedriver automatically (Selenium Manager); the
page HTML is inspected with **BeautifulSoup** (`inspector.py`), no
page-side JavaScript.

- **Default:** the automation launches Chrome with its own **persistent
  profile** — a directory of its own, registered in the
  `browser_profiles` table of sarthi.db on first use (default:
  `Backend/skills/browser_awareness/.chrome-profile`, git-ignored; move
  it with `BROWSER_AWARENESS_PROFILE_DIR`). Log in once inside the
  automation window and every later run reuses that session — no more
  guest-like runs. Nothing it does can touch your normal Chrome profile
  or cookies. It opens a visible window of its own so you can watch it
  work.
- **Same Chrome window, new tabs:** start your Chrome with remote
  debugging and set the attach mode — the automation then opens a **new
  tab** inside the already-running Chrome (the window where Sarthi's chat
  may be open):

  ```bash
  set BROWSER_AWARENESS_CDP_URL=http://127.0.0.1:9222
  # launch Chrome first with:
  #   chrome.exe --remote-debugging-port=9222
  ```

  Each command opens its own tab and closes it when the run ends. There
  is no new tab per **ai_chain** command — the laptop RPA drives the
  pages it opens in place. **Future work:** reuse one dedicated browser
  tab (or the same tab) for consecutive browser-awareness commands
  instead of opening a fresh tab each time.

- `BROWSER_AWARENESS_HEADLESS=1` hides the automation window.
- `BROWSER_AWARENESS_PROFILE_DIR=C:\path\to\dir` chooses where the
  persistent automation profile lives (wins over the database entry).
  If the database is unavailable the run falls back to a temporary
  profile, deleted when the run ends.

## Voice feedback (live progress)

Real runs announce progress out loud through `utils.voice` (Windows
SAPI / PowerShell TTS, log-only elsewhere) — the same voice contract
the AI chain uses when it takes over the laptop:

> "Browser awareness started. Opening example.com." → "Clicking Pricing."
> → "Done. The pricing page is open."

Browser awareness drives **its own** browser session, so the "hands
off the keyboard and mouse" warning does not apply — but you still
hear the automation start, what it does at each step (in plain words,
never element ids or typed values), and how it ended. Test mode and
dry runs never speak.

## Safety

- Page content sent to Hermes is a compact, sanitized snapshot — capped
  text and element list, no full HTML/DOM, no passwords/tokens/values.
- Hermes output is validated against the current page snapshot (element
  must exist, visible, enabled, and match the action kind).
- High-impact actions (purchases, sending, deletion-like submits) are
  **never executed without confirmation** — the run stops with a
  `needs_confirmation` result instead.
- Non-http(s) navigation, hidden/disabled elements and non-generated
  selectors are refused.

## Running the tests (no browser or model needed)

```bash
python -m pytest tests/test_browser_awareness.py -q
python -m pytest -q                 # whole Sarthi suite
```

All tests use fake providers/components and pure logic — Selenium,
Playwright, Chrome and the local Ollama model are not required.

## Trying it live

Install the browser stack once (already done in the venv for this
project):

```bash
pip install beautifulsoup4 selenium   # Selenium Manager fetches chromedriver
# or: pip install playwright          # fallback stack, uses installed Chrome
```

Then run Sarthi (test mode first to see the plan, no browser opens):

```bash
python -m brain... # or via the Chat UI
/browse example.com and find the More Information link
```

For a full end-to-end check: launch Sarthi (`start.bat`), make sure the
local Hermes model is running (Ollama, e.g. `hermes3:8b`), and send
`open example.com and find the More Information link` in the Chat UI.
The status text shows each phase: opening → inspecting → Hermes
observation → validated action → done. Set `BROWSER_AWARENESS_CDP_URL`
if you want the actions to appear as new tabs in the Chrome window you
are already using.

## Layout

| File | Responsibility |
| ------ | ---------------- |
| `schemas.py` | typed contracts + pure safety gate (`validate_inspection`) |
| `page_snapshot.py` | pure, sanitized snapshot builder + Hermes text block |
| `inspector.py` | Playwright JS walk + BeautifulSoup (Selenium) inspectors (lazy imports) |
| `selenium_page.py` | Selenium→Playwright-style page adapter (locator/goto/inner_text) |
| `hermes_inspector.py` | Hermes Browser Awareness Agent + strict JSON validation |
| `executor.py` | validated action executor + selector allow-list |
| `manager.py` | inspect → observe → validate → execute → reinspect loop |
| `driver.py` | browser session lifecycle (isolated launch / CDP attach) |
| `main.py` | `BrowserAwarenessSkill` (BaseSkill entry point) |

The extension point for future **skill learning** is intentionally left
open: a `BrowserTaskState`-shaped result could later be distilled into a
reusable per-site skill after a validated, successful workflow.
