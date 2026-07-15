---
name: ui-evaluator
description: Run evidence-backed UI acceptance. Use after generating a page, or when the user wants a design review or recirculatable critique against declared goals and success criteria.
---

# ui-evaluator

**Evaluator** contract: turn **declarations** into checks. Do not invent new taste standards. Every issue **points back** to a declaration.

## Steps

### 1. Bind declarations

Identify which of these apply to this surface (repo files, prior turns, or design-playbook defaults):  
`spec` · `domain` · `craft` · `design` · `components` · `template`.

**Done when:** the check set is named; if `spec` L6 exists, every criterion and its required proof are on the list.

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
| Required proof exists for each L6 item | `spec` |

Rubric notes: [`references/rubric.md`](references/rubric.md).

Record an evidence ledger before writing findings:

```text
criterion: <L6 item or bound declaration>
required:  <declared proof>
observed:  <artifact, interaction, check result, or missing>
result:    pass|fail|blocked|N/A
```

For implemented UI, visible-state proof is a rendered inspection at the declared target viewport; behavior proof is an interaction trace or automated check; code-health proof is the relevant available test, type/lint, or affected build result. Planning-only proof is declaration coverage and must not claim a render or test occurred.

**Done when:** every bound row was considered; every required proof has a ledger entry; skips are explicit (“N/A: no risk fields”); unavailable required proof is `blocked`, not skipped.

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

- **Pass:** zero blocking; every required evidence row passes; L6 items tickable; token gaps logged or fixed.
- **Recirculate:** each blocking `source` names the step/declaration to reopen in design-playbook.

**Done when:** pass/recirculate is stated; every blocking finding has a closure trail - `recirculate -> fix -> re-eval -> 0 blocking` - or, only after an explicit user decision, is accepted with a recorded reason that points to the user's statement or decision record. Without a user in the loop, blocking findings remain in recirculate and the run requests a decision. Blocking sources are non-empty when not pass.

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
