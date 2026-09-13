# Audit — Sandbox failure analysis & fixes

Date: 2026-09-03

This audit documents the investigation of the failed tasks recorded in
`sandbox/` and every change made to the project as a result. It also lists the
sandbox cleanup that was performed.

---

## 1. What the sandbox showed

`sandbox/failed_tasks.log` (cleanup run 2026-08-26) recorded **11 failed tasks**,
all with the same signature:

- Provider: `Ollama`
- Model: `hermes3:8b`
- Trace error: `"Connection timeout"`
- Duration: ~63s (range 62s – 111s) — i.e. a timeout firing right at ~60s

Examples of the prompts that failed: "hello", "how are you ?", "hey ??",
"how tell me who you are /remember you are sarthi", "open youtube and search
praxx analysis".

### Root cause

- Before commit `1ece9b9` (2026-08-27), `hermes/providers/local_provider.py`
  sent Ollama requests with `timeout=self._config.timeout` = **60s**
  (verified via `git show 1ece9b9^:hermes/providers/local_provider.py`).
- `hermes3:8b` runs on CPU and routinely needs **60–150s+** per generation, so
  any slow generation was killed at the 60s read timeout → `Connection timeout`.
- Commit `1ece9b9` introduced a dedicated `local_timeout` (default **180s**) in
  `hermes/config/settings.py` + `loader.py` and switched the Ollama client to
  it. This is why the *identical* prompts succeeded right after 2026-08-27
  (sandbox records show completions in 15s – 153s, some >100s).
- Two gaps remained and could reproduce the same user-visible failure:

  1. **Web UIs hard-aborted long before the model finishes**: `UI/chat.html`
     aborted `/hermes/chat` after **30s** and `UI/dashboard.html` aborted
     `/command` after **15s** — both far below real local-model latency. Users
     saw "timed out", retried the same prompt, and generated the duplicate
     error runs visible in the sandbox.
  2. **No resilience for cold model loads**: the first request after Ollama
     starts pays a model-load penalty (observed: first "hello" 111s, subsequent
     15s). On a slower machine even 180s could be exceeded once.

---

## 2. Code changes made

### 2.1 `hermes/providers/local_provider.py` — retry once on timeout

`LocalHermesProvider.generate()` now runs the request through a new
`_attempt(task)` helper and **retries once when the failure is a pure timeout**
(`error == "Connection timeout"`). Rationale: the model is warm by the second
attempt, so a slow first call (cold model load) no longer fails the whole task.

- A warning is logged when the retry triggers.
- **Non-timeout errors are never retried** (HTTP errors such as "model not
  found", connection errors, invalid payloads, unexpected errors) — nothing is
  pointlessly double-run, and tool side effects are never re-executed.
- No config change required; the 180s `local_timeout` budget from the earlier
  fix is unchanged.

### 2.2 `UI/chat.html` — raise the Hermes question abort timeout

`sendHermesQuestion()` aborted the `/hermes/chat` fetch after 30s.

- Abort raised from **30s → 300s**, with a comment explaining the local model's
  60–180s+ latency and that the cap only guards against a genuinely hung server
  (the backend's own `local_timeout` governs success/failure).
- The timeout error message was updated to reflect the new wait: *"The model
  still hasn't responded after 5 minutes. Check that Ollama is running and
  healthy, then try again."*

### 2.3 `UI/dashboard.html` — raise the command timeout

`dashSendCommand()` aborted the `/command` fetch after 15s.

- Abort raised from **15s → 300s** for the same reason (commands routed to
  Hermes/NLP can take minutes on a CPU model).

### 2.4 `scripts/clean_sandbox.py` — prune index records of deleted successes

`clean_sandbox.py` already deleted successful task **directories** while
keeping failed ones, but left the successful task's **index records** behind
when the query still contained failures — leaving `sandbox/index.json` pointing
at directories that no longer exist (the sandbox viewer would 404 on them).

- The loop now rebuilds each partially-cleaned query with only its failed
  records, so a query that keeps failures never references deleted successes.

### 2.5 `brain/executor.py` — same pruning fix for the in-app `/clean` handler

`BrainExecutor._handle_clean` (the `/clean` slash command) duplicated the same
cleanup logic and had the same stale-record bug.

- Applied the identical fix: successful records are dropped from queries that
  still contain failed records.

### 2.6 `tests/test_local_provider.py` — regression tests for the retry

Three new tests lock the retry behavior:

- `test_retries_once_on_timeout_then_succeeds` — a first-attempt timeout is
  retried once and the warm retry succeeds (asserts exactly 2 calls).
- `test_does_not_retry_more_than_once_on_timeout` — two consecutive timeouts
  still fail with the standard `"Connection timeout"` error (asserts 2 calls
  max, not an infinite loop).
- `test_non_timeout_errors_are_not_retried` — an HTTP error (404 "model not
  found") fails immediately with exactly 1 call.

---

## 3. Sandbox cleanup performed

Ran the project's own cleanup tooling (plus manual removal of one leftover):

- `python scripts/clean_sandbox.py --apply` (twice — the second run after the
  2.4 pruning fix removed the leftover success index records):
  - **56 successful ("gone through") task records deleted** along with their
    directories under `sandbox/tasks/`.
  - **13 failed records kept for review** across 6 queries in
    `sandbox/index.json`.
- Manually removed `sandbox/tasks/task_local_000001/` (a successful run that
  was never indexed, so the cleaner skipped it).
- On-disk failed task directories kept as evidence: `task_721bf9`,
  `chat_d2291b36`. The other kept failures (`task_39da56`, `chat_797be05f`,
  etc.) had no directories left on disk; their records remain in
  `sandbox/index.json` and `sandbox/failed_tasks.log`.

Final state of `sandbox/index.json`: 6 queries, 13 error-only records.

---

## 4. Verification

- Full test suite: **381 passed** (`pytest -q`, run twice — after the provider
  change and again after the executor/cleanup changes).
- Targeted tests (provider, conversation history, hermes API, chat modes,
  sandbox query index, brain engine): all green.
- `ruff check` and `ruff format --check` clean on all touched Python files
  (`hermes/providers/local_provider.py`, `brain/executor.py`,
  `scripts/clean_sandbox.py`, `tests/test_local_provider.py`).
- Line endings (CRLF) preserved in all edited files.

---

## 5. Files touched in this session

| File | Change |
| --- | --- |
| `hermes/providers/local_provider.py` | Retry once on `Connection timeout` (cold model load); extracted `_attempt()` |
| `UI/chat.html` | Hermes question abort 30s → 300s + accurate timeout message |
| `UI/dashboard.html` | Command abort 15s → 300s |
| `scripts/clean_sandbox.py` | Prune index records of deleted successful tasks |
| `brain/executor.py` | Same pruning fix in the `/clean` handler |
| `tests/test_local_provider.py` | 3 new retry regression tests |
| `sandbox/index.json` | Cleaned: 56 successes removed, 13 failures kept |
| `sandbox/tasks/task_local_000001/` | Deleted (unindexed successful run) |
| `audit.md` | This document |

> Note: `skills/browser/main.py` and `sandbox_test/` also show as modified in
> `git status`, but those changes predate this session and are unrelated to the
> sandbox failure analysis.
