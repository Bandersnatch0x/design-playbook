# rules-governance — paper walkthrough (vNext S5)

Paper fixture for the project-level append-only governance log
(`rules-governance.jsonl`, living next to the persistent contract). It
demonstrates one full learning-and-governance chain (rules-prototype 9.2):
the same in-flight re-trigger finding derived as a candidate across 3
distinct runs / 2 task contexts / 0 unexplained false positives, then two
user adjudications — promote to `advisory`, and after the advisory
evidence period promote to `machine-enforced` with all six promotion
criteria recorded.

- Schema, event enum, and validation live in
  `packages/design-playbook/scripts/rules_governance.py` (first-version
  schema; the S1 spec placed it in slice 1 — S5 is the landing).
- The candidate side is **derived, never stored**: the queue comes from
  run history via `learning_candidates.py` (same "derive from history, no
  new persistent state" precedent as assumed aging).
- Append discipline: events are only appended; `id` is stable and unique;
  `supersedes` points at an earlier event; decisive events carry
  `decided_by: user` — an agent may never write them; recomputable counts
  stay in the derived view, not in this log.
- `ST-01` is the walkthrough's promoted rule; it is intentionally not in
  the shipped registry — the governance log is project history, and the
  registry entry lands with a later release (G8 checks registry -> log
  references, not the reverse).
