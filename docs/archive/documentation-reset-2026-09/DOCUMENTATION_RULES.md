# Documentation rules

These rules govern every document in `docs/` (this tree). They were applied
during the 2026-09-13 documentation reset and must be followed for future
edits.

1. **Code is the implementation source of truth.** A claim is only
   documentation when a file path backs it.
2. **ARCHITECTURE.md describes observed architecture** — the system as it
   is, never as it should be.
3. **PROJECT_STATE.md describes current implementation state** — working,
   partial, and broken, each labelled.
4. **VISION is separate from implementation reality.** Aspirational content
   does not belong in canonical documents.
5. **Planned features must never be described as implemented.** They live in
   PROJECT_STATE.md's PLANNED section with placeholder evidence.
6. **Experimental components must be marked experimental** (or their
   status class stated: EXPERIMENTAL/PARTIAL/UNUSED).
7. **Deprecated architecture must not remain in canonical documents.** When
   code changes, the describing document changes in the same change.
8. **Any major architecture change requires a documentation update** —
   new loop, new registry, removed subsystem, changed data contract.
9. **Documentation must identify uncertainty instead of inventing
   certainty.** Unknowns are stated as unknowns (see FORENSIC_SUMMARY.md).
10. **Historical documentation belongs in `docs/archive/`.** Superseded
    documents are archived or deleted at reset time, never edited in place.

## Maintenance conventions

- Line references in documents cite the state at last verification; prefer
  naming functions over line numbers where drift is likely.
- Inventories (SKILLS.md, TOOLS.md, API.md, DATABASE.md) must be regenerated
  by inspection — not edited from memory — when the underlying surface
  changes.
- DIVERGENCE.md, DUPLICATION.md and DEAD_CODE.md record findings; they never
  prescribe fixes. Decisions belong in code review, after which entries are
  updated or removed.
- The sandbox (`sandbox/`, `Backend/sandbox/`) and `results/` contain runtime
  data, not documentation — never index or archive them here.
