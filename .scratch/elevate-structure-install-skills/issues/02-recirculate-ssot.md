# 02 - Recirculate table single source of truth

**What to build:** The recirculate (observable -> declaration) map is owned by `ui-evaluator` only; the `design-playbook` orchestrator keeps a one-line pointer, not a duplicated table. Editing acceptance no longer drifts from the orchestrator.

**Blocked by:** None - can start immediately

**Status:** implemented (pending commit)

- [x] `ui-evaluator` SKILL holds the authoritative recirculate table (observable -> declaration)
- [x] `design-playbook` orchestrator replaces its recirculate table with a one-line pointer to `ui-evaluator`
- [x] No observable->declaration pair appears in both skills
- [x] `native-craft` row present in the authoritative table
- [x] Recirculate step in orchestrator still reads correctly via the pointer

## Implementation notes

- Added "## Recirculate map (authoritative)" section to `ui-evaluator/SKILL.md` with the 8-row observable->declaration table (incl. `native-craft`).
- Replaced the orchestrator's 8-row `## Recirculate` table with a one-line pointer.
- Verified: no recirculate row leaked back into the orchestrator (grep clean).
- `ui-evaluator` keeps its distinct "Run checks" (Check->Source) table - that is the acceptance checklist, a different step from the recirculate routing; co-located, not duplicated.

## Review (standards + spec, inline; no git)

- **Spec:** matches 04-P1 decision (SSOT in ui-evaluator).
- **Standards:** resolves the Divergent Change smell (cross-skill dual-write) flagged in code review; writing-great-skills single-source-of-truth satisfied.
- **Commit:** deferred to ticket 06.

Unblocks: **04** (sixth dogfood gate).
