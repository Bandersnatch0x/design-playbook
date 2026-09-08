---
description: Build a static run handoff from an explicit run and its declared Fill
---

# run-handoff

Build the existing static delivery package for one explicit Design I/O run. Not a pipeline obligation and not acceptance.

## Usage

```text
python <plugin>/scripts/run_handoff.py <run> [--fill <declared-path>] [--round N] [--summary <text>] [--lang zh-CN|en] [--json]
```

- `<run>` is required. Do not discover a run from `.scratch/`.
- Read `fill:` declarations from that run's `plan.md` (unfenced column-0 lines). One declared Fill is used automatically; multiple require `--fill` with one of those declared paths; none or a missing/ineligible declaration fails with repair guidance.
- Do not scan the project for HTML, and do not use preview or reference assets as the reviewed Fill.
- The existing Evidence builder writes `evidence/static-handoff/` (delivery page, Fill copy, archive, disclosure, snapshots). Report `verdict`, `authority`, and `confirmationSource` verbatim, including `Pending`, `blocked`, `not-applicable`, and `unsubstantiated`.
- Do not write acceptance or convert a non-Pass state into Pass.
- Page language: explicit `--lang`, then `DPB_PREVIEW_LANG`, then `LANG`, otherwise Chinese. Unknown environment locales use the same Chinese default as Preview. Language affects UI labels only; machine fields, original diagnostics, and user-authored content remain verbatim.

## Done when

The user asked for a handoff; `index.html` exists under the selected run tree; and `verdict` / `authority` / `confirmationSource` were reported verbatim.

Scope:
$ARGUMENTS
