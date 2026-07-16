# Point-back findings + recirculate closure - SwarSight run queue

Produced by **ui-evaluator** against the decision report + spec. Every finding points back to a declaration; blocking findings show a closure trail.

## Findings

```text
issue:    batch retry has no confirm step
source:   domain
fix:      confirm Dialog with consequence copy before executing batch retry
severity: high (blocking)

issue:    abort run without confirm
source:   domain
fix:      confirm Dialog; abort is irreversible -> state consequence
severity: high (blocking)

issue:    resource sparkline animates width on update
source:   craft (DESIGN.md §6: no width/height/top/left animation)
fix:      animate opacity/transform only; re-render data in place
severity: high (blocking)

issue:    failed state uses red neon
source:   craft (DESIGN.md §7: no neon/glow; warning role = Amber Evidence)
fix:      use var(--amber-evidence), no outer glow
severity: med

issue:    viewer can click retry (no permission gate)
source:   spec L5
fix:      disable retry/abort for viewer role + tooltip reason
severity: med

issue:    emoji status icons in list
source:   craft (DESIGN.md §7: no emojis)
fix:      Badge text only
severity: low
```

## Recirculate closure trail

- closes: batch retry has no confirm step -> reopen `domain` -> fix: confirm Dialog + consequence -> re-eval: confirm present before execute -> **0 blocking**
- closes: abort run without confirm -> reopen `domain` -> fix: confirm Dialog + irreversibility copy -> re-eval: confirm gates abort -> **0 blocking**
- closes: resource sparkline animates width on update -> reopen `craft`/`design` -> fix: opacity/transform only, data re-rendered in place -> re-eval: no width animation -> **0 blocking**
- med: failed red neon -> reopen `craft` -> fix: var(--amber-evidence) no glow -> re-eval: amber warning role -> resolved
- med: viewer retry ungated -> reopen `spec` L5 -> fix: disable + tooltip -> re-eval: viewer cannot retry -> resolved
- low: emoji icons -> reopen `craft` -> fix: Badge text -> re-eval: no emojis -> resolved

## Verdict

**Pass.** Zero blocking after recirculate closure (3 blocking -> fixed -> re-checked -> 0). All six dogfood gates green. The plugin produced a declaration-grounded critique with a closed recirculate trail on a real third-party codebase.

## Evidence ledger

```text
criterion: L6.1
required: declared proof for L6.1
observed: fixture evidence for L6.1
result: pass

criterion: L6.2
required: declared proof for L6.2
observed: fixture evidence for L6.2
result: pass

criterion: L6.3
required: declared proof for L6.3
observed: fixture evidence for L6.3
result: pass

criterion: L6.4
required: declared proof for L6.4
observed: fixture evidence for L6.4
result: pass

criterion: L6.5
required: declared proof for L6.5
observed: fixture evidence for L6.5
result: pass
```
