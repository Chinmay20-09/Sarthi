---
name: power-loss-recovery
description: Set up a laptop to record a recovery note and shut down when AC power is lost, or explain what is needed to do so safely.
---

# Power loss recovery and shutdown

Use this skill when asked to prepare for an electricity outage by recording recoverable work state and shutting down the laptop after AC power is lost.

## Important operating limits

A skill does not run continuously. To react to a power cut, configure an operating-system-level watcher that runs independently of Codex and detects the transition from AC to battery. Do not claim monitoring is active unless the watcher has actually been installed and enabled.

A background watcher cannot read Codex's live conversation or save unsaved documents in other apps. A recovery note can record information available to the watcher, such as a timestamp, battery level, and a user-designated project status file. For Codex work, create or update a recovery note while Codex is active, and explain that it will not automatically include later conversation or unsaved work unless a supported integration is configured. Never promise that open applications or unsaved files will be saved.

## Setup workflow

When asked to set this up:

1. Identify the operating system and confirm that its power-status interface can distinguish AC power from battery. Prefer a native, read-only power event or status API.
2. Agree on a recovery-note location and the useful project information to record. Keep logs local and avoid copying secrets, credentials, or unrelated personal data.
3. Prepare the watcher and recovery-note behavior for review before enabling it. Use the least-privileged mechanism available. Keep the watcher limited to detecting AC loss, writing the agreed recovery details, and requesting an orderly shutdown.
4. Explain the shutdown timing and how the user can cancel it. Prefer a short grace period with a documented cancel method so a transient disconnect does not immediately close the session. Do not disable system safeguards or force-close applications.
5. Enable the watcher only when the user has asked for setup. Verify its configured state and explain how to stop, remove, or inspect it. Do not claim the shutdown path was tested unless it was actually tested safely.

If the OS cannot reliably identify AC loss, or the requested work log depends on inaccessible Codex or app state, explain the limitation and offer a narrower recovery log. Do not substitute battery-percentage heuristics for direct AC status when a direct status is available.

## When an outage is reported while Codex is active

Before shutting down, record a concise recovery note from the current conversation and accessible workspace: what was being done, key decisions, files changed, remaining steps, and relevant commands. Write it to the agreed local location. Then request an orderly OS shutdown only if the user has asked for shutdown in this situation and the recovery note was written successfully. Tell the user what was saved and whether shutdown was initiated.
