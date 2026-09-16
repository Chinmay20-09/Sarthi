# Sarthi — local-first AI desktop assistant

**Sarthi** is an AI assistant that runs on your own computer. You type or
speak a command in plain language — "open youtube and search lofi",
"remember my wifi password is X", "chain write a poem from chatgpt to gemini"
— and Sarthi figures out what to do and does it on your machine.

Everything stays local: your commands, memories and conversation history live
in a database on your disk, and by default the AI model that handles complex
requests runs locally (Ollama) rather than in the cloud.

## What Sarthi can do

- **Open and close applications and websites** — "open chrome",
  "open youtube and search lofi", "close chrome"
- **Talk with you** — conversation mode for plain chat, backed by a local or
  cloud AI model
- **Remember things** — "remember key: value", then "recall key" later
- **Voice** — speak commands (speech-to-text) and hear spoken replies
  (text-to-speech)
- **Automated browsing** — for websites it doesn't know, Sarthi can open the
  site in Chrome and inspect the page to complete your request
- **AI chaining (hands-off automation)** — send a prompt to one AI website,
  then feed its reply to another ("run … from chatgpt to gemini")
- **Project tracking** — track GitHub-backed projects and get summaries
- **App scanning** — discovers your installed applications so "open <app>"
  works with the apps you actually have
- **A dashboard in your browser** — chat, history, memory, knowledge and
  settings pages served by the app itself

## How it works (the short version)

When you type a command, Sarthi first tries a **fast, deterministic path** —
a local rule-based pipeline that handles the commands it knows reliably
(open, close, search, play, remember, …). Only when a request is too complex
or ambiguous for that path does it escalate to **Hermes**, a bounded AI agent
that can reason about the request and use a small set of whitelisted tools.
Actual actions on your computer (launching apps, typing, managing processes)
are performed by a separate execution layer — never by the AI model directly,
and there is no shell or arbitrary-code execution anywhere.

## Where to start

1. **[INSTALLATION.md](INSTALLATION.md)** — requirements, installation,
   starting Sarthi, and the external software you may need.
2. **[USAGE.md](USAGE.md)** — the commands and features you can use today.
3. **[FAQ.md](FAQ.md)** — common questions and known limitations.

If you want to look under the hood or work on the code, see
[`docs/dev/`](../dev/README.md).
