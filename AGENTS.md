# Agents

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community
structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or
instructions before doing anything else.

Rules:

- For codebase questions, first run `graphify query "<question>"` when
  graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for
  relationships and `graphify explain "<concept>"` for focused concepts. These
  return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw
  grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates;
  dirty graph files are not a reason to skip graphify. Only skip graphify if the
  task is about stale or incorrect graph output, or the user explicitly says not
  to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of
  raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when
  query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current
  (AST-only, no API cost).

## Desktop task routing

- For supported Windows desktop actions, Sarthi's backend is the deterministic
  task router and executor. Resolve one action directly without starting
  Hermes/model orchestration. For example, `play lost in love on YouTube`
  should resolve the first video and have the desktop client open its watch
  URL, while
  `turn sad` should select the matching Hitori pet image through the desktop
  client.
- Start Hermes/model orchestration for desktop actions only when the user
  gives a compound request that needs decomposition, such as `turn sad and
  play lost in love on YouTube`. Hermes may convert that request into ordered
  smaller tasks; the backend must validate every task against its explicit
  supported-action allowlist before execution. Hermes must not execute desktop
  actions, run arbitrary code, or bypass the Desktop Hand/client action
  boundary.
- Keep each resulting action deterministic and execute it through the
  appropriate validated boundary: Desktop Hand for backend-controlled Windows
  actions, or an explicitly validated client action for GUI-local behavior
  such as changing the pet image or opening the user's browser.
