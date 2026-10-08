# Desktop Hand

The **physical execution layer** of Sarthi. The Brain decides what should
happen; the Desktop hand performs the actual computer interaction.

```
Brain  →  Executor / Skill  →  DesktopHand  →  Windows
```

Desktop is **not** a reasoning engine: it executes explicit, validated
operations and reports structured results. Failures are returned, never
hidden.

## Usage

```python
from hands.desktop import DesktopHand

desktop = DesktopHand()

# Structured result dict on every call
result = desktop.execute("open_application", target="Chrome", path=r"C:\...\chrome.exe")
# {"success": True, "action": "open_application", "target": "Chrome",
#  "message": "Application launched: Chrome", "data": {"pid": 1234, "path": "..."}}

desktop.execute("open_url", url="https://example.com")
desktop.execute("type_text", text="hello")
desktop.execute("copy", text="clipboard payload")
result = desktop.execute("read_clipboard")   # data.text
desktop.execute("list_windows")              # data.windows
desktop.execute("get_processes")             # data.processes
desktop.execute("read_file", path=r"C:\Users\me\notes.txt")   # scope-checked
```

Convenience wrappers exist for the most common actions and return the
same structured dict: `open_application`, `close_application`, `open_url`,
`type_text`, `press_key`, `hotkey`, `copy`, `paste`, `click`,
`move_mouse`, `read_clipboard`, `get_active_window`, `list_windows`,
`get_processes`, `launch_process`.

## Capabilities

Actions are allow-listed per capability (`capabilities.py`). Unknown
actions and malformed arguments are rejected before anything runs; no
arbitrary kwargs pass through, and no shell or code execution exists at
any layer.

| Capability | Status | Actions |
| --- | --- | --- |
| APPLICATION_LAUNCH | implemented | open_application |
| APPLICATION_CLOSE | implemented | close_application |
| WINDOW_READ | implemented | list_windows, get_active_window |
| BROWSER_CONTROL | implemented | open_url (http/https only) |
| KEYBOARD | implemented | type_text, press_key, hotkey |
| MOUSE | implemented | move_mouse, click (explicit coordinates only) |
| CLIPBOARD | implemented | copy, paste, read_clipboard |
| FILESYSTEM_READ | implemented | read_file, list_directory (scoped) |
| FILESYSTEM_WRITE | implemented | write_file, delete_file (scoped) |
| PROCESS_CONTROL | implemented | get_processes, launch_process, terminate_process |
| WINDOW_CONTROL | planned | — |
| SHELL | planned (needs review gate) | — |

## Browser rule

The hand never guesses coordinates as a strategy. For browser interaction
the project priority is:

```
DOM / browser automation  →  accessibility / semantic UI
                          →  visual/UI automation
                          →  coordinate fallback (calibrated, never random)
```

Element discovery lives in **Browser Awareness** (`skills/browser_awareness/`)
and the ai_chain DOM layer (`skills/automation_engine/ai_chain/`); Desktop
provides only the physical primitives at the end of that chain
(`open_url`, `type_text`, `click`).

## Safety boundaries

- No shell execution, no arbitrary Python execution — ever.
- Paths and pids are explicit; name→path resolution happens upstream in
  the knowledge layer, not inside the hand.
- Filesystem operations are scoped to allowed roots
  (`FilesystemBackend(allowed_roots=[...])`, default: user profile) with a
  1 MB read/write cap.
- Every action is logged: `[Desktop] action=... target=... status=...`
- Optional backends (pyautogui, pyperclip, pywin32) degrade to structured
  failures — the hand never pretends success.

## Dependencies

- **Core** (always available): `psutil` — already a project dependency.
- **Optional** (`pip install -e ".[automation]"`): `pyautogui`, `pyperclip`
  for keyboard/mouse/clipboard; `pywin32` for window enumeration.

## Independence

`desktop_agent.py` (repo root) runs this hand standalone — the seam for a
future `Sarthi.exe` desktop runtime. A clean local IPC boundary (e.g. a
small HTTP or named-pipe endpoint over `DesktopRequest`/`DesktopResult`)
can be added there later without touching Brain modules.
