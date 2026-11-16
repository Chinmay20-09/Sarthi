# Archive summary

This folder contains old project documents. They record past designs, audits, and development work. They do not describe the current system. Read [current developer documentation](../dev/README.md) for current behavior.

## September 2026 documentation reset

The folder `documentation-reset-2026-09/` contains the documents that the project used before the reset on 2026-09-16. The reset merged many separate guides into the current architecture, project-state, development, and testing guides.

The old architecture, runtime flow, module map, and data flow became [Architecture](../dev/ARCHITECTURE.md). The old skill, tool, agent, knowledge, memory, database, browser, automation, API, configuration, and dependency guides also became part of that document.

The old capability and project-state reports became [Project State](../dev/PROJECT_STATE.md). The old test guide became [Testing](../dev/TESTING.md). User setup and usage information moved to `docs/client/`.

## Audit and decision history

The archive keeps these records for reference:

- `ARCHITECTURAL_DECISIONS.md` records decisions AD-01 through AD-16 and their reasons.
- `CONSOLIDATION_PLAN.md` and `CONSOLIDATION_REPORT.md` record the 2026-09 documentation and architecture consolidation.
- `DIVERGENCE.md`, `Divergance-matrix.md`, `DEAD_CODE&Duplicate.md`, and `FORENSIC_SUMMARY.md` record audit findings from 2026-09-13 and 2026-09-14.
- `BRAIN_HAND_BOUNDARY_REPORT.md` records the review before Desktop Agent IPC was added.

Older project snapshots and audits are in the archive root. They record earlier project states.

## Archive rule

Do not edit archived files to match current code. Add new historical records in a dated folder. Keep current behavior in `docs/dev/`.
