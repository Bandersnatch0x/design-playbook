---
description: Cross-run review of Design I/O runs — gate table + repeat blockers
---

Cross-run **run review** over `.scratch/<run>/` dirs in the user project. Not a step of a single Design I/O run. Markdown only; report header **`run-review/v1`**.

## Discover

Scan user-side `.scratch/<run>/` (not monorepo `dogfood/*` globs). **Include** only dirs that have `point-back.md` (one table row each). List dirs without `point-back.md` as skipped + reason — they contribute **0** rows. If runs-with-point-back **< 2**, refuse and report that N.

## Report (tables, in order)

1. **Inclusion manifest** first: `path | status` (`included` / `skipped` + reason). Note: hash match ≠ honest transcription of `observed`.
2. **Per-run table** — mandatory **run-path** column; other columns as needed; **gate** from real `validate_run.py` exit when the script is present (plugin install: `packages/design-playbook/scripts/validate_run.py` per run); else literal `not checked`. **Never** infer ok from "artifacts look complete".
3. **Repeat blockers** — pure frequency table `count | runs | observed text` (verbatim first-seen text). A **repeat blocker** is the same normalized `observed` text recurring across runs (**counting, not judging**). Rows only where ledger `result != pass`. Grouping key = `observed` **casefold + whitespace-collapsed**, then **char-for-char** equality only; `count ≥ 2`. Literal differences stay separate; optional `similar:` pointer line, never merge counts. **`_none_` is normal** when nothing qualifies (do not loosen normalization to manufacture repeats).
4. **Point-back** cites: path + verbatim `observed:` quote; no line numbers.
5. Rollup numbers derived **row-by-row** from the tables above — no "overall it seems".

Ledger row shape: **ui-evaluator** step 2 (do not restate).

```
禁止:
- no new run ledger
- no prose lessons / narrative "learning"
- no auto-writeback to baseline
- no semantic clustering of observed — verbatim grouping only
```

Scope:
$ARGUMENTS
