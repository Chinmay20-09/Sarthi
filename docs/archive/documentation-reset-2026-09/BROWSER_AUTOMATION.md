# Browser automation audit (observed)

Three distinct browser mechanisms coexist. Documented as they are; no
recommendations.

## Stack 1 — BrowserSkill (default browser, deterministic)

- **Where**: `skills/browser/main.py`
- **Mechanism**: `webbrowser.open` — the OS default browser. Also builds
  search URLs (`google.com/search?q=...`, `youtube.com/results?search_query=...`).
- **Used for**: "open X", "search Y", "play Z" — the deterministic fast path.
- **Network**: one `urllib.request` for favicon/URL verification in the
  search-and-save flow.

## Stack 2 — Browser Awareness (isolated Chrome, DOM-level)

- **Where**: `skills/browser_awareness/`
- **Mechanism**: Selenium (primary, `selenium_page.py` +
  Selenium Manager chromedriver) with Playwright as fallback backend
  (`driver.py` picks via `BROWSER_AWARENESS_DRIVER`, auto-detect otherwise).
  Page HTML parsed with BeautifulSoup (`inspector.py`). A CDP direct-attach
  mode exists (`BROWSER_AWARENESS_CDP_URL`).
- **Used for**: `browse` intents on non-deterministic domains
  ("open example.com and find the pricing page") and the `browser_ask` Hermes
  tool. Manager loop: snapshot → Hermes observation → schema-validated action.
- **Profile**: isolated per-session profile by default;
  `browser_profiles` table + `database/profiles.py` manage a persistent
  `default` profile (logins remembered); `BROWSER_AWARENESS_PROFILE_DIR`
  overrides. Headless flag `BROWSER_AWARENESS_HEADLESS`.
- **Never**: coordinate guessing. Coordinates appear nowhere in this stack.

## Stack 3 — ai_chain (automation Chrome + RPA hybrid)

- **Where**: `skills/automation_engine/ai_chain/`
- **Mechanism**:
  1. `control.py` launches a dedicated Chrome with
     `--remote-debugging-port` and a persistent profile
     (`ai_chain/.chrome-profile/`); PyAutoGUI drives clicks/typing; the
     `keyboard` lib registers the Ctrl+Alt+X abort hotkey; pyperclip for
     clipboard.
  2. v1.5 DOM assist: `dom.py` + `selenium_dom.py` (Selenium over
     debuggerAddress; Playwright fallback) read `page_source`, parse with
     BeautifulSoup, resolve the target element, convert its box to a
     window-fraction point for PyAutoGUI. Fallback: v1.0 estimate + grid scan
     + Ctrl+A page copy.
  3. v1.7 `browser_automation.py` — a fully DOM-driven navigation/click/
     copy/paste engine with verification and `ChainState` (clipboard,
     extracted_values). **No production caller** (library + tests only).
- **Used for**: AI chains (ChatGPT → Gemini etc.).

## Mechanism usage matrix

| Mechanism | BrowserSkill | Browser Awareness | ai_chain |
| --------- | ------------ | ----------------- | -------- |
| webbrowser.open | ✓ | — | — |
| Selenium | — | ✓ primary | ✓ (DOM read attach) |
| Playwright | — | ✓ fallback | ✓ fallback reader |
| BeautifulSoup | — | ✓ | ✓ |
| PyAutoGUI | — | — | ✓ (input) + hands/desktop input |
| requests | — | — | — (httpx2 used elsewhere) |
| screenshots | — | — | — (reads DOM, not pixels) |
| coordinates | — | — | window-fraction points derived from DOM boxes (legacy fallback: estimates + grid scan) |

## Shared infra

- `hands/desktop/browser.py` opens URLs as a DesktopHand action (used by the
  `close`/agent seam, not by the three stacks above).
- Both Selenium stacks rely on lazy imports: without the `browser` extra the
  app imports and tests run fine (graceful degradation is test-locked).
