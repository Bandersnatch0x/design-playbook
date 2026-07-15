# Decision report - SwarSight simulation run queue

Produced by **ui-picker**, before any code. Grounded in SwarSight `DESIGN.md` tokens (Abyss Canvas #080A0D, Graphite Surface #0D1117, Signal Cyan #2DD4BF accent, Amber Evidence #F2C94C warnings; cockpit-dense; no emojis; no neon/glow; transform/opacity motion only).

```text
scene: ops list / dashboard (simulation run queue)
density: cockpit-dense (8/10 per DESIGN.md)
template: ops list — summary + main run list + side trends + batch action bar
regions:
  top: running/failed/queued/completed counts + time-window filter
  main: run list (state, scenario, owner, duration, resource sparkline, actions)
  side: failure trend, queue pressure, recent failure causes
  actions: batch retry / abort (appears on selection)
components:
  run state        -> Badge (queued/running/paused/failed/completed/aborted/timeout)
  failed / timeout -> Amber Evidence color (DESIGN.md warning role), not red neon
  resource usage   -> read-only mini sparkline (Tag-style chip, not a card)
  scenario / owner -> text + muted telemetry color
  retry            -> Button (recovery action, not a Tag)
  abort            -> Button (danger, confirm-gated)
  run detail       -> Drawer (dense read-only, not a Dialog: non-interrupt)
  batch retry      -> Button in action bar + confirm Dialog (interrupt)
risks:
  - retry/abort without confirm -> domain dangerous op (blocking if missing)
  - sensitive sim params in detail -> mask by default (domain)
  - resource sparkline animating width -> violates DESIGN.md "no width animation" (craft/design)
  - viewer can retry -> spec L5 permission gap
tokens:
  bg: var(--abyss-canvas) / panel: var(--graphite-surface) / border: var(--ash-border)
  accent: var(--signal-cyan) (single accent, selected/focus/primary only)
  warning: var(--amber-evidence)
  text: var(--cold-ink) / muted: var(--muted-telemetry)
  no emojis, no glow, no purple-blue gradients (DESIGN.md anti-patterns)
```

Do not start implementation until this report exists. Confirmed present -> proceed to fill.
