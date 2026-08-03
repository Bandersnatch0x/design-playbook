# OPP-21 — Fix distinct-run repeat-blocker counting

Status: open
Type: task
Source: product-surface roundtable 2026-08-03 (`.scratch/product-surface-roundtable-2026-08-03/roundtable.md`)

## Problem

`scripts/aggregate_runs.py` counts a repeat blocker by incrementing `count` per non-pass ledger row, and only deduplicates the `runs` list. The domain definition (CONTEXT: `repeat blocker`; `commands/run-review.md` on the v0.10 branch) is "the same normalized `observed` text **across runs**". A single run with two identical non-pass `observed` rows therefore produces `count>=2` and is reported as a repeat blocker, even though it is one run.

## Reproduction (verified 2026-08-03)

One run dir with two ledger rows (`observed: Same blocker` / `Same   blocker`, results `blocked` + `fail`) yields:

```json
{"runs_total": 1, "repeat_blockers": [{"text": "Same blocker", "count": 2, "runs": ["2026-01-01-one-run"], "results": {"blocked": 1, "fail": 1}}]}
```

Current 20-run dogfood corpus has `repeat_blockers=0`, so this is not an active false alarm upstream, but it will corrupt future systemic-defect signals and invalidates `aggregate_runs.py` as a full oracle for the v0.10 `run-review` command comparison.

## What to build

- Red test in `tests/test_aggregate_runs.py`: single run with two equivalent non-pass `observed` rows must NOT produce a repeat blocker.
- Make `count` equal the number of **distinct runs** (not ledger rows) for the blocker key; keep per-result row-level statistics under a separately named field if still wanted.
- Update the `markdown_view` count semantics if needed; keep the normalization exactly as-is (char-for-char after casefold + whitespace collapse).

## Acceptance

- New red→green test above.
- `python scripts/aggregate_runs.py --md` on the real corpus still shows `_none_` (20 runs, 0 repeats).
- `tests/test_aggregate_runs.py` full suite passes.

## Evidence

- `scripts/aggregate_runs.py` `aggregate()` blocker loop (count += 1 per row; runs dedup).
- Reproduction output above.
- Domain definition: CONTEXT `repeat blocker`; v0.10 `commands/run-review.md` (on `feature/v0.10-run-review`).

## Kill criterion

Only if the domain definition is deliberately changed to "recurring rows" instead of "across runs" — the current CONTEXT and v0.10 command text explicitly say across runs.

## Comments

- Created 2026-08-03. Fix belongs on `main` (repo-only tool, no installable surface).