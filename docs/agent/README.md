# agent/ — sprint context for coding agents

This directory contains the **active sprint/task context** for CLI coding
agents working on Sarthi. It answers three questions:

1. What is the current project context? → [CURRENT_CONTEXT.md](CURRENT_CONTEXT.md)
2. What exactly am I doing? → [TASK.md](TASK.md)
3. What rules must I obey? → [CONSTRAINTS.md](CONSTRAINTS.md)

## Important

- **This is temporary.** It is a context package for the current sprint and
  may be replaced when the next sprint starts.
- **Historical versions belong in `docs/archive/`** (e.g. a
  `sprint-XX/` folder), not in this directory.
- **This must not become a second copy of the developer documentation.**
  Permanent technical truth lives in [`docs/dev/`](../dev/README.md) — keep
  `CURRENT_CONTEXT.md` concise and link to `dev/` instead of duplicating it.
- Keep only what the agent needs *right now*: current architecture pointers,
  sprint-relevant implementation state, relevant files, active blockers.
