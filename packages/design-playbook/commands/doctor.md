---
description: Diagnose installed design-playbook capability and repairs
---

# doctor

One packaged diagnosis entry for install/runtime capability.

```text
python <plugin>/scripts/doctor.py
python <plugin>/scripts/doctor.py --json
python <plugin>/scripts/doctor.py --run-root .scratch/<run>
python <plugin>/scripts/doctor.py --repo-root <target-repo>
```

Reports `ok` / `degraded` / `broken`. Failed checks include a concrete repair. Optional adapters (Playwright, run-root env) degrade rather than hard-fail the install. Audit-preference state shows effective stage values, sources, asked status, and corrupt layers for target repository.

`ok` / `degraded` / `broken` describe install and runtime health of the local surface only — they are not a public capability-maturity verdict. Maturity vocabulary (`stable` / `experimental` / `blocked-by-gate` / `not-shipped`) stays with the `run-status` capability receipt; doctor reads existing facts and adds no new health or capability-state authority.
