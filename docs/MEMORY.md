# Memory (observed)

Three distinct memory systems. All persistent state is SQLite (see
DATABASE.md) except the sandbox.

## 1. Long-term user memory (/remember)

- **Where**: `knowledge/memory.py` → `knowledge_memory` table in sarthi.db.
- **Interface**: `/remember key: value` (auto-keys `note_N` when no key given),
  `/recall [key]`, `/forget key` — built-in executor handlers
  (`brain/executor.py:374-445`).
- **Readers**: Hermes retriever (SQL section), Hermes memory_search tool,
  `build_memory_prompt()` injected as a system message into plain chat
  (`hermes/service.py::chat`), `/memory` API for the UI.
- **Deliberately NOT cleared** by chat reset (`api.py:748-762`).

## 2. Conversation memory (sessions)

Two tables, two writers:

| Table | Writer | Reader | Purpose |
| --- | --- | --- | --- |
| `conversation_messages` | `hermes/conversation.py::ConversationStore` (used by plain chat + agent history) | retriever (recent turns), /hermes flows | Hermes' own session continuity |
| `chat_messages` | `POST /chat` (api.py:732) — the UI persists what it rendered | `GET /chat` | dashboard transcript mirror |

Both are cleared together by `DELETE /chat` for a session. **Not a
duplication**: one is the rendered UI transcript, the other is the model's
session context — different shapes of the same exchange, kept separate on
purpose (AD-09, DIVERGENCE D-05).

## 3. Task memory (Hermes sandbox)

- **Where**: `hermes/sandbox.py` → `sandbox/tasks/<task_id>/` +
  `sandbox/index.json` query index, under the **one canonical root**
  `Backend/sandbox` (a relative `HERMES_SANDBOX_PATH` is resolved against the
  backend root, never the cwd — AD-01).
- **Content**: every Hermes/ai_chain task with prompt, response, trace,
  provider/model/status/duration.
- **Readers**: sandbox query retrieval in the agent (`retriever.py`), the
  `/hermes/sandbox` API, `clean_sandbox.py` script.
- **Cleanup**: `/clean` (executor `_handle_clean`) deletes successful tasks,
  keeps failures; `Backend/scripts/clean_sandbox.py` is the CLI twin.

## Retrieval (how memory feeds the model)

`hermes/retriever.py` — hybrid, bounded, no vector DB:

```
query ─▶ retrieve(query, session_id)
          ├─ SQL:        knowledge_memory (LIKE), command_history, settings
          ├─ Knowledge:  applications + websites (exact + fuzzy)
          ├─ Sandbox:    similar past tasks via index.json
          └─ Conversation: recent session turns
       ─▶ ContextBuilder ─▶ bounded, source-tagged text blocks
```

Caps: per-section and overall char limits; failures degrade to empty context.

## Command history

`command_history` table records every `/command` input (api.py). Surfaced via
`GET /command-history`, deletable per entry; searched by the retriever and
history_search tool. Not a memory system per se but feeds retrieval.
