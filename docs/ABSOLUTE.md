# ABSOLUTE — System-Handled Automation

**Status: Binding rule for every Sarthi automation that takes control of
the laptop (keyboard, mouse, or screen).**

When an automation is "system handled", the machine is not yours while
it runs — Sarthi drives it. The user must **never** be surprised by the
system moving on its own, and **never** be left unsure whether they can
touch their keyboard and mouse again.

## The rule
1.First approach is trying to make any automation is to control device over the approach of API and other paid medium
2.Any automation that takes control of input devices **must**:

### 1. Announce before it starts (voice feedback)

Before the first mouse move or keystroke, Sarthi must **say out loud**
that it is taking over and tell the user to step away from the laptop.

> *"Hands off. Automation started. Please step away from the keyboard
> and mouse while Sarthi is working."*

This is announced **voice first**, together with the on-screen
HANDS-OFF banner and a countdown that gives the user time to comply.

### 2. Keep the user informed while it runs

- The on-screen banner stays visible for the whole run.
- Every step is logged (`utils.logger`) so a user can retrace what the
  system did and where it saved its results.
- The user can always abort:
  - a global abort hotkey (`Ctrl+Alt+X`), and
  - a mouse failsafe (moving the mouse into a screen corner).

### 3. Announce when it is over (voice feedback)

On **every** terminal state — completed, failed, or aborted — Sarthi
must **say out loud** that the user has the machine back.

> *"Automation finished. You can use your computer now."*

The spoken completion prompt is the user's signal that hands-off mode
has ended — they do not have to watch the screen to know.

### 4. Always release control

No matter how the run ends (success, failure, exception, abort), the
automation must release its input locks/hotkeys and return control to
the user. Sarthi never leaves the user locked out of their own machine.

## Implementation

| Concern | Where |
|---|---|
| Voice announcements (start / done) | `utils/voice.announce()` — Windows SAPI via pywin32, PowerShell `System.Speech` fallback, log-only elsewhere. Never raises. |
| HANDS-OFF banner, countdown, abort hotkey, failsafe | `skills/automation_engine/ai_chain/` (`chain.py`, `control.py`) |
| Governed automation (reference implementation) | AI Chain — drives ChatGPT → Gemini by taking over the laptop |
| Spoken phrases | see `skills/automation_engine/ai_chain/chain.py` (`VOICE_HANDS_OFF`, `VOICE_DONE`) |

## Voice feedback for future automations

Any new automation that takes over the machine **must** follow this
contract. Minimum skeleton:

```python
from utils.voice import announce

announce("Hands off. Automation started. Please step away from the keyboard and mouse.")
try:
    ...  # the automation, with abort support ...
finally:
    announce("Automation finished. You can use your computer now.")
```

Notes:

- Announcements are **synchronous** so the voice finishes before the
  next action starts.
- Dry runs / test mode **never** announce and **never** touch the
  machine — voice and control are only for real runs.
- Keep phrases short; they are spoken, not read.
