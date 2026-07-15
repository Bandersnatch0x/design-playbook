---
name: ui-evaluator
description: Declaration-backed UI acceptance. Use after generating a page, or when the user wants design review or a recirculatable critique.
---

# ui-evaluator

**Evaluator** contract: turn **declarations** into checks. Do not invent new taste standards. Every issue **points back** to a declaration.

## Steps

### 1. Bind declarations

Identify which of these apply to this surface (repo files, prior turns, or design-playbook defaults):  
`spec` · `domain` · `craft` · `design` · `components` · `template`.

**Done when:** the check set is named; if `spec` L6 exists, it is on the list.

### 2. Run checks

Walk every applicable row (exhaustive for bound declarations):

| Check | Source |
| --- | --- |
| Empty / loading / error / permission | `spec` |
| Risk color, secrets, dangerous ops | `domain` |
| AI slop, hierarchy, purposeless motion | `craft` |
| Raw hex / px / ms (unlogged) | `design` |
| Badge/Tag, Dialog/Drawer, … | `components` |
| Shell matches scene | `template` |
| Each L6 acceptance item | `spec` |

Rubric notes: [`references/rubric.md`](references/rubric.md).

**Done when:** every bound row was considered; skips are explicit (“N/A: no risk fields”).

### 3. Emit point-back findings

```text
issue:    <observable>
source:   <declaration>
fix:      <next edit>
severity: high|med|low
```

Order: **blocking** first (broken L5/L6, unsafe dangerous ops, removed focus rings), then polish.

**Done when:** every finding has all four fields; no “generally improve the design” lines.

### 4. Verdict

- **Pass:** zero blocking; L6 items tickable; token gaps logged or fixed.  
- **Recirculate:** each blocking `source` names the step/declaration to reopen in design-playbook.

**Done when:** pass/recirculate is stated; every blocking finding has a closure trail - `recirculate -> fix -> re-eval -> 0 blocking` - or is explicitly accepted by the user with a recorded reason. Blocking sources are non-empty when not pass.

## Recirculate map (authoritative)

Single source of truth for the observable -> declaration routing. The orchestrator and other skills point here; do not duplicate it.

| Observable | Declaration |
| --- | --- |
| Happy path only; empty/fail/auth missing | `spec` |
| Wrong business meaning / risk / secrets | `domain` |
| AI slop, flat hierarchy, purposeless motion | `craft` |
| Scattered hex/px/ms | `design` |
| Badge↔Tag, Dialog↔Drawer mixups | `components` |
| Wrong page shell (e.g. list as card wall) | `template` |
| Desktop app feels like a web page / wrong seam | `native-craft` |
| Critique with no owner | re-run `ui-evaluator` |

Fix only the owning layer, then resume from the pipeline step that consumes it.

## Guard

Prefer positive fixes in `fix`. Reserve bans for non-negotiables (e.g. open dangerous action without confirm) and always pair with the required behavior.
