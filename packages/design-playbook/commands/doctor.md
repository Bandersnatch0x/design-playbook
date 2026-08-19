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
