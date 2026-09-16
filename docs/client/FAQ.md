# FAQ

User-facing questions and known limitations. (Developer topics live in
[`docs/dev/`](../dev/README.md).)

## Setup & running

**Sarthi won't start / the page doesn't load.**
Check the server window for errors; confirm Python 3.10+ and that your
virtual environment is active. `python Backend/api.py` prints the actual
error. The dashboard lives at `http://127.0.0.1:8000`.

**Does my command go to the cloud?**
Not by default. Simple commands never touch any AI model. Complex requests
use the configured provider — Ollama running locally by default. A cloud
provider is used only if you set `HERMES_PROVIDER=openrouter` /
`openai_compatible` with a key in `.env`.

**Do I need Ollama?**
Only for complex/AI-answered requests. Install it and run `ollama pull
hermes3:8b`, or switch providers in `.env`. Without any provider, simple
commands (open/close/search/play/remember) still work.

**Why does "open someapp" not find my app?**
Sarthi only knows apps it has scanned. Say `scan apps` (or use the Knowledge
page) and try again. If it's a website, use the browser-search fallback —
Sarthi remembers it for next time.

**Voice input does nothing.**
Install the voice extras (`pip install sounddevice faster-whisper`), allow
microphone access, and check the mic in Windows settings. The first use is
slow while the Whisper model loads.

**I don't hear spoken replies.**
Spoken replies need Windows (SAPI/PowerShell TTS). Check the voice-replies
toggle in Settings.

## Usage

**What's the difference between default and conversation mode?**
Default mode *executes* commands. Conversation mode just *chats* — no tasks
run. Switch with `conversation mode`, back with `/exit`.

**Sarthi searched the web instead of doing my task.**
Sentences that describe a task ("find all assignment PDFs and rename them")
are handed to the AI agent instead of being searched. Sarthi cannot manage
files yet, so the agent will explain that it can't complete such a task
rather than opening a nonsense browser tab.

**An AI chain opened a browser and started typing on its own.**
That's the hands-off automation: a warning and a 5-second countdown always
precede it. Press **Ctrl+Alt+X** or push the mouse into a screen corner to
abort immediately.

**The AI chain failed / typed in the wrong box.**
Log in once to each AI site inside the automation Chrome profile, then
recalibrate: `python -m skills.automation_engine.ai_chain.calibrate`. AI-site
UI changes can also break a calibrated run; recalibrating fixes it.

**How do I stop Sarthi from remembering something?**
`forget <key>` (or delete it on the Memory page). Clearing a chat session
does **not** delete your `/remember` facts — that's intentional.

**Where is my data stored?**
Entirely on your machine: `Backend/database/sarthi.db` (memories, history,
settings, projects) and `Backend/sandbox/` (task records). Nothing is synced.

**Can I use it from another device on my network?**
The server binds to all interfaces, so other machines on your LAN can reach
the dashboard — but there is no login/authentication, so treat it as
home-network-only and never expose it to the internet.

**What is the Desktop Agent / remote mode in the settings?**
An advanced mode where Sarthi sends actions (close app, launch app) to a
separate agent process on another machine over your LAN
(`SARTHI_DESKTOP_AGENT_MODE=remote`). It is a development feature without
authentication — keep it `local` unless you specifically need it.

**Why is a complex question slow?**
It runs on the local model (Ollama by default), which is CPU-bound on most
machines. The agent is also deliberately bounded (a few reasoning turns,
timeboxed). Cloud providers are faster if you configure one.

## Known limitations (summary)

- Windows-centric: voice replies and laptop automation don't work elsewhere.
- Voice input needs manually installed extras (`sounddevice`,
  `faster-whisper`).
- Real AI-chain runs need one-time logins + calibration and are sensitive to
  AI-site UI changes.
- No file operations yet: Sarthi can reason about "rename my files" but
  cannot do it.
- No authentication on the server or the Desktop Agent — LAN/local use only.
- The API port must be changed in two places (`Backend/config.py` and
  `Backend/sarthi.bat`) if you move off 8000.
- Disabling a skill via the Skills page resets on restart.
