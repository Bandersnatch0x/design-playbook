# Showcase - design-playbook on SwarSight

A real end-to-end **Design I/O** run against [SwarSight](https://github.com/) (swarm-intelligence foresight platform; React + Tailwind + shadcn workbench). The plugin was loaded from this package and driven against a one-line ask. Screenshots + artifacts below are the actual pipeline output.

**Ask:** `在 SwarSight 加一个模拟运行队列监控页：看每个模拟任务的状态、失败重试、资源占用。`

## Screenshots (every key step)

### Step 0 · Install
![Install](screenshots/00-install.png)

### Step 1 · ux-spec → six-layer spec
![Spec](screenshots/01-spec.png)

### Step 2 · ui-picker → decision report (before code)
![Decision report](screenshots/02-decision-report.png)

### Step 3 · ui-evaluator → point-back + recirculate closure
![Point-back](screenshots/03-point-back.png)

### Result · six gates green
![Six gates](screenshots/04-gates.png)

## Source artifacts

1. [`01-spec.md`](01-spec.md) - six-layer spec (ux-spec)
2. [`02-decision-report.md`](02-decision-report.md) - shell + component decision (ui-picker)
3. [`03-point-back.md`](03-point-back.md) - point-back findings + closure (ui-evaluator)

## Six gates (all green)

| Gate | Pass |
| --- | --- |
| L5/L6 before pretty UI | ✅ |
| Decision report before code | ✅ |
| Point-back evaluator findings | ✅ |
| No skip of Done when | ✅ |
| Generalizes (SwarSight domain) | ✅ |
| Recirculate closure (blocking → fix → re-eval → 0) | ✅ |

## Regenerate screenshots

```bash
node scripts/screenshot-showcase.mjs   # repo-root script; needs playwright-core + chromium (see header)
```

## Reproduce in your session

```text
/plugin marketplace add <owner>/<repo>
/plugin install design-playbook@design-playbook
/design-playbook:design-io 在 SwarSight 加一个模拟运行队列监控页
```
