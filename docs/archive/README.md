# Archive

Historical documentation, preserved rather than deleted. Nothing in this tree
describes the *current* system — read [`docs/dev/`](../dev/README.md) for
that.

## Contents

### documentation-reset-2026-09/

The complete documentation system as it stood on 2026-09-16, before it was
consolidated into the four-layer structure (`client/`, `dev/`, `agent/`,
`archive/`). Also includes the 2026-09-13/14 forensic audit trail.

**Consolidated into active documentation:**

| Archived document | Content now lives in |
| --- | --- |
| ARCHITECTURE.md, RUNTIME_FLOW.md, MODULE_MAP.md, DATA_FLOW.md | [`dev/ARCHITECTURE.md`](../dev/ARCHITECTURE.md) |
| SKILLS.md, TOOLS.md, AGENTS.md, API.md | [`dev/ARCHITECTURE.md`](../dev/ARCHITECTURE.md) |
| KNOWLEDGE.md, MEMORY.md, DATABASE.md | [`dev/ARCHITECTURE.md`](../dev/ARCHITECTURE.md) |
| BROWSER_AUTOMATION.md, CHAINING.md, AUTOMATION.md | [`dev/ARCHITECTURE.md`](../dev/ARCHITECTURE.md) |
| CONFIGURATION.md, DEPENDENCIES.md, CLI.md | [`dev/ARCHITECTURE.md`](../dev/ARCHITECTURE.md) + [`client/INSTALLATION.md`](../client/INSTALLATION.md) (user-facing parts) |
| PROJECT_STATE.md, CAPABILITIES.md, DIVERGENCE.md, DEAD_CODE&Duplicate.md, FORENSIC_SUMMARY.md | [`dev/PROJECT_STATE.md`](../dev/PROJECT_STATE.md) + [`dev/ARCHITECTURE.md`](../dev/ARCHITECTURE.md) |
| TESTING.md | [`dev/TESTING.md`](../dev/TESTING.md) |
| DOCUMENTATION_RULES.md | philosophy/rules now summarized in [`dev/README.md`](../dev/README.md) |

**Historical-only (audit trail, kept for the reasoning):**

- ARCHITECTURAL_DECISIONS.md — full decision log AD-01…AD-16 with
  problem/evidence/rejected-alternatives (referenced by
  `dev/ARCHITECTURE.md` and `dev/PROJECT_STATE.md` for the "why")
- CONSOLIDATION_PLAN.md, CONSOLIDATION_REPORT.md — the 2026-09-14
  architectural consolidation pass (before/after, findings, phases)
- Divergance-matrix.md, DIVERGENCE.md, DEAD_CODE&Duplicate.md,
  FORENSIC_SUMMARY.md — the forensic audit: what was found, resolved,
  deferred
- BRAIN_HAND_BOUNDARY_REPORT.md — the 2026-09-15 Brain/Hand boundary report
  (AD-16); superseded by the 2026-09-16 IPC implementation, but records the
  inspection trail
- README.md — the old documentation index

### Pre-reset documents (from the earlier archive)

- ABSOLUTE.md — a superseded behaviour contract (e.g. voice-announcement
  rules the code outgrew)
- ARCHITECTURE.md, ARCHITECTURE_NOTES.md, PROJECT_STATE.md, README.md,
  README_ENV.md, CHANGELOG.md, CONTRIBUTING.md — older snapshots of the
  project's self-description
- old-project-README.md (in `documentation-reset-2026-09/`) — the former
  top-level project README preserved from `docs/archive/README.md`
- audit.md, AUDIT_CHECKLIST.md, AUDIT_REPORT.md — earlier audit passes

## Rules

- Archived documents are never edited in place or kept in sync with the code
  — they are frozen history.
- New archives are added as dated folders (e.g. `sprint-XX/` for historical
  agent-sprint contexts, or a future `documentation-reset-YYYY-MM/`).
