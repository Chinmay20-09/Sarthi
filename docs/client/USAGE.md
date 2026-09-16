# Usage

Everything you can do with Sarthi today. Type commands in the desktop client,
the web dashboard chat, or speak them (voice input).

## Command modes

- **Default mode** — commands are executed ("open chrome").
- **Conversation mode** — plain chat with the AI, no task execution. Enter it
  by typing `conversation mode` (also `talk mode` / `chat mode`); return with
  `/exit`. In the dashboard you can also click the mode badge.

## Everyday commands

| Say / type | What happens |
| --- | --- |
| `open chrome` / `open spotify` | Launches an installed application |
| `open youtube` | Opens a known website |
| `open youtube and search lofi` | Opens a site and searches on it |
| `open youtube and play <song>` | Opens a site and plays on it |
| `close chrome` | Closes a running application |
| `scan apps` | Re-scans installed applications into Sarthi's knowledge |
| `remember wifi: mypassword` | Saves a memory (auto-keyed `note_N` if you omit a key) |
| `recall wifi` | Recites a memory (plain `recall` lists recent ones) |
| `forget wifi` | Deletes a memory |
| `chain write a poem from chatgpt to gemini` | Hands-off AI chaining: asks ChatGPT, feeds the reply to Gemini |
| `automate <query> from claude to grok` | Same, other supported AIs |
| `generate assistant for <skill>` | Generates an assistant config from a skill's manifest (experimental) |
| `clean` | Clears successful task records from the sandbox (failures are kept) |

**Slash commands**: `/remember`, `/recall`, `/forget`, `/chain`, `/exit`,
`/help` where applicable. Unknown input falls through to conversational
fallback, so plain questions ("what is the capital of France?") get chat
answers.

**Compound commands**: sentences with multiple steps ("open youtube and
search lofi") are split and executed in order; the response shows one step
card per action.

## Sites supported by AI chaining

`chatgpt`, `gemini`, `claude`, `perplexity`, `grok`, `deepseek`, `copilot`
(plus common aliases). Without `from X to Y`, the default is
`chatgpt → gemini`. Real runs need one-time logins inside the automation
Chrome profile and per-machine calibration (`python -m
skills.automation_engine.ai_chain.calibrate`). A hands-off warning with a
5-second countdown precedes every run; press **Ctrl+Alt+X** (or slam the
mouse into a screen corner) to abort.

## Voice usage

- **Voice input**: click the mic button in the desktop client/dashboard (or
  run `python Backend/main.py` for a terminal voice loop). Speech is
  transcribed locally (Whisper) and runs through the same pipeline as text.
- **Voice replies**: Sarthi speaks every response aloud by default. Toggle
  it in the dashboard settings page or via the voice-replies setting.
- Requirements: a microphone; the voice extras installed
  (`pip install sounddevice faster-whisper`); Windows for spoken replies.

## The web dashboard

With the backend running, open <http://127.0.0.1:8000>:

| Page | What you do there |
| --- | --- |
| Chat | Talk to Sarthi; switch conversation mode; complex questions are answered by the AI agent with tool use |
| Dashboard | System overview and metrics |
| History | Past commands; delete individual entries |
| Knowledge | The apps/websites Sarthi knows; categorize (favourite/ignored); "Run Anyway" for gated apps; browser-search fallback remembers unknown sites |
| Memory | The facts you saved with `/remember`; delete entries |
| Settings | Voice replies toggle, GitHub username, etc. |
| Skills | The 10 registered skills; enable/disable a skill at runtime |

The desktop client (tkinter app) offers the same chat/command experience in a
native window.

## Project tracking

1. Set your GitHub username in Settings (or "set github_username to …").
2. Add a project in the Projects page (name + GitHub URL).
3. Sync the project to fetch repo data; ask Sarthi about your projects
   ("show my projects", project status questions) — the tracker skill and
   the AI agent can both use this context.

## Other features

- **Unknown-app fallback**: "open <thing>" for an unknown app offers a choice
  card — scan for it, or browser-search it (remembered for next time).
- **Test mode**: the dashboard's test runner sends 60 sample prompts through
  the pipeline in dry-run mode with system telemetry — a safe way to see what
  Sarthi understands without anything executing.
- **Google Calendar connector**: OAuth connection via the Connectors settings
  (the only connector implemented today).
- **Skills on/off**: disable a misbehaving skill from the Skills page; the
  change is runtime-only (resets on restart).

## Things to keep in mind

- Sarthi is **local-first**: your memories, history and task records stay on
  your disk (`Backend/database/sarthi.db`, `Backend/sandbox/`).
- Complex requests are answered by the local AI model (Ollama by default);
  the first complex request can take a while on CPU-only machines.
- A long search-like request that describes a *task* ("find all assignment
  PDFs and rename them") is sent to the AI agent instead of being searched
  literally — and since Sarthi cannot manage files yet, the agent will say
  so rather than doing it.
- See [FAQ.md](FAQ.md) for known limitations and troubleshooting.
