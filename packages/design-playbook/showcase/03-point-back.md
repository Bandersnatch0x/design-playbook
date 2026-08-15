# Point-back findings + recirculate closure - SwarSight run queue

Produced by **ui-evaluator** against the decision report + spec. Every finding points back to a declaration; blocking findings show a closure trail.

## Findings

```text
issue:    batch retry has no confirm step
source:   domain
fix:      confirm Dialog with consequence copy before executing batch retry
severity: S3
disposition: blocking

issue:    abort run without confirm
source:   domain
fix:      confirm Dialog; abort is irreversible -> state consequence
severity: S3
disposition: blocking

issue:    resource sparkline animates width on update
source:   craft (DESIGN.md §6: no width/height/top/left animation)
fix:      animate opacity/transform only; re-render data in place
severity: S3
disposition: blocking

issue:    failed state uses red neon
source:   craft (DESIGN.md §7: no neon/glow; warning role = Amber Evidence)
fix:      use var(--amber-evidence), no outer glow
severity: S1

issue:    viewer can click retry (no permission gate)
source:   spec L5
fix:      disable retry/abort for viewer role + tooltip reason
severity: S1

issue:    emoji status icons in list
source:   craft (DESIGN.md §7: no emojis)
fix:      Badge text only
severity: S1
```

## Evidence ledger

```text
criterion: L6.1
required: rendered failed-row detail shows reason, resource peak, and retry
observed: evaluator report records all three in the expanded Swarsight run row
result: pass

criterion: L6.2
required: interaction trace shows retry success moving failed to queued and onward
observed: evaluator report records failed -> queued -> running/completed states
result: pass

criterion: L6.3
required: rendered no-runs state is non-blank and exposes a next-step CTA
observed: evaluator report records the empty-state message and CTA
result: pass

criterion: L6.4
required: viewer retry and abort controls are unavailable with an explanation
observed: evaluator report records disabled viewer actions and their reason
result: pass

criterion: L6.5
required: batch retry executes only after consequence-bearing confirmation
observed: closure trails record confirmation copy before retry and abort execution
result: pass
```

## Positive findings

- All five L6 criteria pass in the Evidence ledger above (failed-row detail, retry state trace, empty-state CTA, viewer gating, confirm-before-batch-retry).
- Every finding is declaration-grounded (`domain` / `spec` L5 / `craft` DESIGN.md tokens) — none required free-floating judgment.

## Recirculate closure trail

- closes: batch retry has no confirm step -> reopen `domain` -> fix: confirm Dialog + consequence -> re-eval: confirm present before execute -> **0 blocking**
- closes: abort run without confirm -> reopen `domain` -> fix: confirm Dialog + irreversibility copy -> re-eval: confirm gates abort -> **0 blocking**
- closes: resource sparkline animates width on update -> reopen `craft`/`design` -> fix: opacity/transform only, data re-rendered in place -> re-eval: no width animation -> **0 blocking**
- S1: failed red neon -> reopen `craft` -> fix: var(--amber-evidence) no glow -> re-eval: amber warning role -> resolved
- S1: viewer retry ungated -> reopen `spec` L5 -> fix: disable + tooltip -> re-eval: viewer cannot retry -> resolved
- S1: emoji icons -> reopen `craft` -> fix: Badge text -> re-eval: no emojis -> resolved

## Coverage statement

必审: primary path findings 6/6 complete
未审: none (single-viewport walkthrough)

## Limitations statement

- Single-viewport walkthrough of the queue page; findings derive from declaration-grounded inspection of rendered states, with no involved-user evidence.

## Verdict

**Pass.** Zero blocking after recirculate closure (3 blocking -> fixed -> re-checked -> 0). All six dogfood gates green. The plugin produced a declaration-grounded critique with a closed recirculate trail on a real third-party codebase.
