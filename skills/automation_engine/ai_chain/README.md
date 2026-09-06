# AI Chain (laptop-controlled)

A sub-module of the Automation Engine that chains two AIs by **taking
control of your laptop** — Sarthi moves the mouse and keyboard itself:

1. **AI1** (default: ChatGPT) receives your query.
2. **AI1's reply** is pasted into **AI2** (default: Gemini) as the prompt.
3. Every response — and the image Gemini generates, when asked — is
   saved to a run folder under `results/ai_chain/`.

```
"You: make an image of the sarthi workflow"
   └─▶ ChatGPT (AI1): "Write an image prompt for the sarthi workflow…"
          └─▶ Gemini (AI2): [receives that prompt, generates the image]
                 └─▶ saves: query.txt, responses, downloaded image
```

> **Example command:** "chain make an image of the sarthi workflow from
> chatgpt to gemini"

## ⚠️ Hands-off mode

This module follows **docs/ABSOLUTE.md** — the binding rule for
system-handled automation. Before moving the mouse, Sarthi:

1. **says it out loud** (voice feedback via `utils.voice.announce`):
   *"Hands off. Automation started. Please step away from the keyboard
   and mouse while Sarthi is working."*
2. prints a **HANDS-OFF warning** banner and a 5-second countdown.

While it works, **do not touch your keyboard or mouse** — it may click
and type into the wrong place.

**Abort at any moment with:**

- `Ctrl+Alt+X` — clean abort (saved work so far is kept), or
- slam the mouse into **any screen corner** — PyAutoGUI failsafe.

When the chain finishes — completed, failed, or aborted — Sarthi
**tells you out loud** that you can use the computer again
(*"Automation finished. You can use your computer now."*), so you do
not need to watch the screen to know when hands-off mode ends.

## What it needs from you (first run)

- Chrome (or your default browser) where you are **logged in** to
  [chatgpt.com](https://chatgpt.com) and
  [gemini.google.com](https://gemini.google.com).
- Do not run anything full-screen over the browser while it works.## How it reads replies (no OCR)

v1.5, the module reads the page **HTML** first: it attaches read-only to
the running Chrome (DevTools protocol) and **regexes the page's HTML**
for the exact strings that mark the affordances it needs — `Copy`,
`Send`/composer, `Download` — then clicks the real spot (see *v1.5 —
DOM-aware locating* below). Where the site registers one (see *Browser
awareness registry* below), it clicks the message's **Copy** button so
the clipboard holds ONLY the reply — no Ctrl+A of the whole website on
every poll. Otherwise it clicks into the chat area, presses `Ctrl+A` /
`Ctrl+C`, and takes the text after the last occurrence of the prompt it
sent. It polls until the copied text stops changing, which means the AI
finished streaming. For Gemini image generation it gives the image its
full time budget, then clicks the download affordance and harvests the
newest file from your Downloads folder.

Because there is no screen OCR or vision yet, fallback reads are
**coordinate and clipboard based** — which is why calibration exists.

### Browser awareness registry (`registry.py`)

Per-site knowledge of *actions* the robot can perform — today: how to
copy the assistant's reply. Each site ships a `CopyAffordance`:

```python
{
  "method": "button",
  "label": "Copy",
  "point": [0.88, 0.87],
  "scan_region": [0.60, 0.72, 0.96, 0.92],
  "retries": 9
}
```

- `label` names the affordance semantically (what a future vision/OCR
  locator would search for);
- `point` is the primary locator — the window-fraction click point of
  the button (defaults are estimates; calibrate for your monitor);
- `scan_region` is the fallback: when the point misses, the driver
  clicks a small grid across this box (window fractions `x0, y0, x1, y1`
  around the last message), nearest cells first, and takes the first
  click that puts text on the clipboard — a Copy button is the only
  thing that does that;
- `retries` caps the total click attempts (point + scan cells) before
  falling back to the page copy.

When the button copy comes back empty the driver falls back to the
Ctrl+A/Ctrl+C page copy, so unregistered sites and UI changes degrade
gracefully instead of breaking. Override any affordance in
`calibration.json` without touching code:

```json
{
  "actions": {
    "chatgpt": {
      "copy": {"method": "button", "label": "Copy", "point": [0.9, 0.85], "retries": 8}
    }
  }
}
```

The scan region can also be set per site with
`AI_CHAIN_<SITE>_COPY_SCAN_REGION="0.6,0.72,0.96,0.92"` (or
`AI_CHAIN_<SITE>_COPY_POINT="0.9,0.85"` for the point).

### v1.5 — DOM-aware locating (`dom.py`, regex over the page HTML)

Instead of clicking estimated points and hoping, v1.5 **reads the page's
HTML** and regexes it for the words that identify the affordance
("copy", "type", "download" and friends) — exactly what a vision
system would search the screen for, but in the markup:

- the assistant message's **Copy** button: `aria-label="Copy"`,
  `data-testid="...copy..."`;
- the **composer** you type into: `id="prompt-textarea"` (ChatGPT),
  `aria-label="Enter a prompt here"` (Gemini), `id="chat-input"`
  (DeepSeek), `placeholder="Ask anything..."` (Perplexity),
  `contenteditable="true"` (Claude) — with a generic
  `contenteditable="true"` fallback on every site;
- Gemini / Grok / Copilot's image **Download** button:
  `aria-label="Download"`.

When Chrome is running with a DevTools debugging port, the driver
attaches read-only (it never navigates, types or clicks through CDP —
the mouse is still the same PyAutoGUI robot, so hands-off mode,
Ctrl+Alt+X and the failsafe behave identically) and pulls the live HTML
with one `evaluate`: `document.documentElement.outerHTML` plus the
found element's bounding box. The regex match becomes a precise
window-fraction click point instead of an estimate.

**Enabling:** start Chrome with a debugging port (the whole point is
attaching to the browser you are already logged into):

```bash
chrome.exe --remote-debugging-port=9222
```

or set the URL in the environment. When the port is unreachable — or
Playwright is not installed — nothing breaks: every locator returns
`None` and the driver silently uses the v1.0 point+scan+Ctrl+A path.

Per-site regex matchers live in `registry.py` (`DEFAULT_DOM_PROFILES`);
override them via `calibration.json` under `actions.<site>.dom` without
touching code:

```json
{
  "actions": {
    "chatgpt": {
      "dom": {
        "copy": [
          {"tag": "button", "attribute": "aria-label", "value_pattern": "^copy$"}
        ]
      }
    }
  }
}
```

Environment switches:

- `AI_CHAIN_CDP_URL` — DevTools endpoint (default `http://127.0.0.1:9222`)
- `AI_CHAIN_DOM=0` — master switch: disable all DOM locating
- `AI_CHAIN_<SITE>_DOM_<ACTION>=0` — disable one action per site
  (`COPY`, `COMPOSER`, `DOWNLOAD`); e.g. `AI_CHAIN_GEMINI_DOM_COPY=0`

### Browser awareness (screen state + local Hermes model)

The robot never guesses blindly about the browser screen — it classifies
what each Ctrl+A/Ctrl+C copy actually contains before acting:

- **Write side:** after pasting a prompt it copies the composer back and
  checks the paste landed in the message box (re-focusing and retrying
  up to 3 times) before pressing Enter. A missed paste — the click did
  not hit the composer — fails in seconds with a *recalibrate the
  composer point* hint instead of silently waiting out the whole budget
  on a new-chat page.
- **Read side:** the copy is classified against per-site markers. A
  **login wall**, a **new-chat landing** (prompt never sent) or a
  **still-loading** page is recognised deterministically and fails fast
  with a precise message; a copy too small to be a page (a message
  element captured whole) is re-read before anything is concluded.
- Only transcripts that really look like a conversation but that the
  heuristic failed to parse go to the **local Hermes model** (Ollama)
  for extraction. Page chrome is never sent to it. If the model also
  sees no real reply, the step fails with a clear message instead of
  saving chrome as the answer. The call goes straight to the local
  provider, so it costs no API credits and creates no extra sandbox
  records.

## Calibration (recommended once per monitor)

Window-fraction defaults usually work, but recording exact spots makes
runs much more reliable:

```bash
python -m skills.automation_engine.ai_chain.calibrate                       # show current values
python -m skills.automation_engine.ai_chain.calibrate --site chatgpt --point composer --record
python -m skills.automation_engine.ai_chain.calibrate --site gemini --point image_download_point --record
```

Points: `composer`, `read_point`, `copy_point`, `image_download_point`
(Gemini only). `copy_point` is the "Copy" button of the newest
assistant message — recording it makes reads copy just the reply
instead of the whole page. Stored in `calibration.json` (git-ignored).
Skipping calibration is fine — the module falls back to estimated
positions.

**Tuning screen awareness:** each site ships word lists that tell the
screen classifier apart a login wall from a new-chat landing from a
loading page (`login_markers`, `landing_markers`, `loading_markers` in
`calibration.py`). When a site changes its UI copy these words go
stale — override them in `calibration.json` without touching code:

```json
{
  "sites": {
    "chatgpt": {
      "login_markers": ["Log in", "Continue with", "Verify you are human"]
    }
  }
}
```

## Triggering

Automation-engine only, e.g. through the Brain / API:

- `chain <query> from <AI1> to <AI2>` (slash or plain speech)
- `/chain <query> from chatgpt to gemini`
- `open <AI1> and <query> ... to <AI2>` — e.g. "open chatgpt and get
  prompt for making birthday invitation image prompt and sendit to gemini"
  (the trailing "send it to ..." marks it as a chain)

In Sarthi **test mode** the command is planned but nothing is touched.
The default pair when "from … to …" is missing is `chatgpt` → `gemini`.

## Supported sites

ChatGPT, Gemini, Claude, Perplexity, Grok, DeepSeek and Microsoft Copilot
all ship v1.5 DOM matchers (and a v1.0 Copy-button point + scan fallback).
Sites without a registered profile still work — the driver falls back to
the Ctrl+A/Ctrl+C page copy. Alias the names you actually say:

```bash
python -m brain.wordfinder add claude anthropic perplexity grok deepseek copilot
```

## Keywords

"open …" targets are delimited by the **wordfinder** keyword DB
(`brain/keywords.json`, gitignored — see `brain/keywords.example.json`
and `python -m brain.wordfinder`). Add words you use often:

```bash
python -m brain.wordfinder add telegram whatsapp
```

## Programmatic use

```python
from skills.automation_engine.ai_chain import run_ai_chain

outcome = run_ai_chain(
    query="make an image of the sarthi workflow",
    ai1="chatgpt",
    ai2="gemini",
    execute=False,   # False = dry-run plan, no laptop control
)
print(outcome.status)   # planned | completed | aborted | failed
print(outcome.message)
```

## Result folder layout

```
results/ai_chain/<timestamp>_<query-slug>/
    01_query.txt
    02_step1_chatgpt_response.txt
    03_step2_gemini_response.txt
    gemini_image_1.png      (if an image was generated & downloaded)
```

## Dependencies

Installed automation stack (already present in the Sarthi venv):

```bash
pip install pyautogui keyboard pyperclip pywin32
```

Each is imported lazily — the module still imports cleanly (and its unit
tests run) on machines without them.

## Known limitations

- Depends on the web UIs' current layout; sites change over time.
- Requires logged-in sessions; a login wall makes runs fail fast with a
  clear message.
- Gemini's download button position needs calibration for best results.
- Reads replies from the clipboard — very long replies are captured in
  full, but pages that render text in shadow-DOM-ish widgets may need
  the copy fallback tuned per site.
