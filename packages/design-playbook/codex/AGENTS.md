# design-playbook for Codex

## Install

Point Codex skills at this package:

```bash
# adjust path
ln -s /path/to/packages/design-playbook/skills/design-playbook ~/.codex/skills/design-playbook
# or copy all of skills/*
```

Or `@` reference:

```text
@packages/design-playbook/skills/design-playbook/SKILL.md
```

## Load order

1. `skills/design-playbook/SKILL.md`
2. Standard order: `ux-spec` → `ui-picker` → `fill` → `craft-guard` → `ui-evaluator`.

Native desktop order: `ux-spec` → `native-craft` → `ui-picker` → `fill` → `craft-guard` → `ui-evaluator`.

Run `native-craft` only for an explicit native-desktop/native-feel target. Web and mobile Web skip `native-craft`; if the platform is unclear, ask before choosing the order. The orchestrator owns the decision gate, render-surface seam handoff, and fail-closed behavior.

Mirror the orchestrator's skip narration (SKILL.md Steps preamble): when a step is skipped, output one line — step name + reason + how to enable, with the gate label when one applies, e.g. `-> preview*: adapter absent, skipped (G5 not triggered; enable via packages/design-playbook-preview/)`.

## Compose

- Style DB → ui-ux-pro-max
- Visual risk → frontend-design
- Pipeline + acceptance → design-playbook
