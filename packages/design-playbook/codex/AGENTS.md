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
2. `ux-spec` → `ui-picker` (+ its `references/*`) → fill → `craft-guard` → `ui-evaluator`

## Compose

- Style DB → ui-ux-pro-max
- Visual risk → frontend-design
- Pipeline + acceptance → design-playbook
