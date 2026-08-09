# ADR-0021: Stage registry module

## Status

Accepted (C4, 2026-08-09)

## Context

Design I/O stage names and artifact filenames are the language agents and
gates already share, but each copy drifts independently:

- `run_status.py` (packaged copy + monorepo root copy, byte-identical) owns
  the `STAGES` table, explicitly mirrored from `SKILL.md` steps with a
  "sync this table" comment.
- `validate_run.py` hardcodes the same artifact names in gate logic and
  owner strings (`evidence/`, `evidence/manifest.jsonl`, `point-back.md`,
  `decision-report.md`, `spec.md`).
- Preview round/confirm/decision filename patterns already have one home in
  `mcp/preview/integrity.py` (C1); the persistent contract's
  `decisions.jsonl` already has one home in `contract_v1.py` (ADR-0017).

Adding one more consumer means hand-syncing another literal set.

## Decision

Ship a package-internal stage registry module at
`packages/design-playbook/scripts/stages.py`:

- `STAGES` — the ordered (key, skill, markers) table currently in
  `run_status.py`, now the single mirror of `SKILL.md` steps.
- Shared artifact-name constants consumed by both `run_status.py` and
  `validate_run.py`: `EVIDENCE_PREFIX`, `EVIDENCE_MANIFEST`,
  `POINT_BACK`, `DECISION_REPORT`, `SPEC_MD`. `STAGES` markers reference
  these constants where they overlap, so the table and the constants
  cannot disagree.
- `run_status.py` (both copies, still byte-identical) imports `STAGES`
  and `POINT_BACK`; `validate_run.py` imports `EVIDENCE_PREFIX` (G6 only,
  this deepening). No gate message text changes.
- Preview presence stays derived by Preview integrity; `decisions.jsonl`
  stays with the persistent contract.

The registry is data + naming authority only: no behavior changes, no new
run-state SSOT.

## Consequences

- One drift surface for stage/artifact naming: change a name in
  `stages.py` and the mirror comment stays correct by construction.
- `run_status`/`validate_run` no longer hand-sync artifact literals.
- Root `scripts/run_status.py` reaches the package registry through the
  existing `_PACKAGE_ROOT` resolution (one more sys.path adapter — the
  known Candidate 5 friction, not fixed here).
- Scripts directory stays non-package; the module is a sibling import
  inside the same scripts dir, plus the existing adapter for the root
  copy.
