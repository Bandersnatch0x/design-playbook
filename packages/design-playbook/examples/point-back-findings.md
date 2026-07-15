# Sample point-back findings + recirculate

Illustrative `ui-evaluator` output. Every issue names a declaration.

```text
issue:    update payment has no confirm step
source:   domain
fix:      Dialog with consequence copy before submit
severity: high

issue:    full card number rendered in form summary
source:   domain
fix:      mask to last-4; explicit reveal only if product allows
severity: high

issue:    empty invoice table is a blank white region
source:   spec
fix:      empty state copy + CTA to billing history help
severity: med
```

## Recirculate (blocking)

1. Open owning declaration (`domain` / `spec` / …).
2. Patch only that layer.
3. Resume pipeline from the step that consumes it (fill or craft).
4. Re-run evaluator → **Done when** zero high/blocking remain (or each remaining item is explicitly accepted by the user).

Do not whole-page restyle to “clear” blocking findings.
