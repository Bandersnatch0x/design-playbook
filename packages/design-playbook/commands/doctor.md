---
description: Diagnose installed design-playbook capability and repairs
---

# doctor

One packaged diagnosis entry for install/runtime capability.

```text
python <plugin>/scripts/doctor.py
python <plugin>/scripts/doctor.py --json
python <plugin>/scripts/doctor.py --run-root .scratch/<run>
```

Reports `ok` / `degraded` / `broken`. Failed checks include a concrete repair. Optional adapters (Playwright, run-root env) degrade rather than hard-fail the install.
