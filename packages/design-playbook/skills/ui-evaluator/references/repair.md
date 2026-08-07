# Narrow repair map

After Recirculate, change the **smallest owning declaration**, re-evaluate only affected L6 criteria, and recapture only invalidated evidence.

| Failure class | Owning declaration | Affected evidence |
| --- | --- | --- |
| Wrong goal / non-goal / always-ask-never | `spec` L1 | All criteria that assumed the old L1 |
| Missing edge path | `spec` L5 | Criteria that name that edge |
| Broken acceptance criterion | `spec` L6.<n> | Only that L6.<n> row + its artifacts |
| Component role mixup | `components` / decision report | Criteria that depend on that role |
| Craft hierarchy / motion | `craft` | Craft-backed criteria only |
| Capture contract / viewport mismatch | observe* seam | Recapture those artifacts (overwrite or revision name) |
| Stale screenshot after Fill change | Fill + observe* | Invalidate bound criteria whose observed UI changed |

## Evidence freshness

- Fill changes that can affect a bound criterion **invalidate** prior evidence for that criterion.
- Replacement artifacts use `overwrite=true` or a new revision filename; the latest manifest entry wins.
- If the ledger still cites a superseded artifact name, emit a **warning** (not a hard Pass) with owner/expected/actual/repair — then recapture or update the ledger.
- Unaffected criteria keep their evidence.
