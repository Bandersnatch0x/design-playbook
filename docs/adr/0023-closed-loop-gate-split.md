# ADR-0023: Closed-loop validation gate split

## Status

Accepted (C6, 2026-08-09). Evidence ledger and Verdict parsing ownership is
superseded by ADR-0025; the gate split, policy ownership, diagnostics, and
orchestration order remain in force.

## Context

`scripts/validate_run.py` grew into a ~1260-line monolith holding every
closed-loop rule set plus the CLI orchestrator in one file:

- G1 spec shape (`check_spec` + `_l6_body` / `_l6_items`),
- G2-G4 point-back / verdict / closure (`check_pointback` + parsing
  helpers, `_check_evidence`, `_verdict`),
- G5 preview confirm (`check_preview` + `_g5_*` helpers, `preview_occurred`),
- G6 evidence binding (`check_evidence` + manifest/ledger helpers plus the
  soft manifest-ts / superseded-artifact warnings),
- `run()` / `_parse_args()` / `main()` orchestration and the optional G7
  import.

Gate modules already exist as one file each: `g7_contract_drift.py` owns the
G7 rule set, `_diagnostics.py` owns the Finding model and projections,
`stages.py` owns `EVIDENCE_PREFIX`, and the runtime modules
(`mcp/preview/integrity.py`, `mcp/evidence/capture_contract.py`) own their
integrity rules (ADR-0022 import seam). Only the G1-G6 rule sets and the
orchestrator share one file — the drift surface every gate edit touches.
Each edit risks changing finding order, message text, or rule IDs that the
seam tests pin down, and review noise grows with file size.

## Decision

Split `scripts/validate_run.py` into focused gate modules plus a thin CLI
orchestrator, one cohesive file per gate (or gate group):

- `scripts/g1_spec.py` — G1: `SPEC_LAYERS`, `_l6_body`, `_l6_items`,
  `check_spec`. The orchestrator imports `_l6_items` here to size the G2
  ledger and G6 binding checks against the same spec read.
- `scripts/g2_g4_pointback.py` — G2-G4: parsing constants
  (`FINDING_FIELDS`, `FIELD_LINE`, `CLOSURE_LINE`, `EVIDENCE_FIELDS`,
  `EVIDENCE_LINE`, `VALID_RESULTS`), `_findings`, `_evidence`,
  `_check_evidence`, `_normalise_issue`, `_verdict`, `check_pointback`.
- `scripts/g5_preview.py` — G5: `preview_occurred`, `_resolve_report_ref`,
  `_g5_no_valid_reason`, `_g5_fact_findings`, `check_preview`. Projects the
  bundled Preview integrity snapshot (C1 / ADR-0004); never owns integrity
  rules.
- `scripts/g6_records.py` — shared G6 input model: `ledger_observed` and
  `manifest_entries`, consumed by both hard-gate and warning policy.
- `scripts/g6_evidence.py` — G6 hard gate: `_g6_capture_findings` and
  `check_evidence`. Validates bound manifest request snapshots through the
  bundled `validate_capture_snapshot` (ADR-0018 enforcement site 3).
- `scripts/g6_warnings.py` — G6 advisory policy:
  `check_manifest_ts_warnings`, `check_superseded_ledger_warnings`, and
  `_ledger_has_evidence_binding`. Consumes `EVIDENCE_PREFIX` from
  `stages.py` (ADR-0021).

`scripts/validate_run.py` keeps exactly the orchestration surface: the
module docstring (usage / strict-mode contract), the one bootstrap (ADR-0022),
`run()` with its finding-aggregation order (G1 -> G2-G4 -> G5 -> G6 ->
warnings -> G7), `_parse_args()` with every CLI flag and help text, `main()`
with exit codes 0/1/2 and the text/JSON projections, and the optional G7
import. `_diagnostics.py` is not moved; rule IDs, message strings, finding
order, exit codes, CLI flags, and help text are preserved byte-for-byte.

Gate modules import `design_playbook.*` absolutely (ADR-0022) and are not
entry points — only the orchestrator (and future consumers) import them.

## Consequences

- One cohesive file per gate; a G6-only change no longer touches G1-G4
  parsing or the CLI. Review surface shrinks per change.
- Finding order stays a single explicit property of `run()`; moving a gate
  call or a finding inside a module is now a visible, reviewable edit.
- Message texts and behavior are unchanged — this is a pure structural
  refactor; the seam test, run-status/stages suites, and full pytest stay
  green. The CI `py_compile` gate lists the new modules.
- New gate rules still land in the gate's own module; the orchestrator stays
  a thin wire-up that new CLI flags extend.
