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

Record an evidence ledger before writing findings. Every L6 criterion has exactly one row:

```text
criterion: L6.<n>
required:  <declared proof>
observed:  <artifact path, interaction, check result, or missing>
result:    pass|fail|blocked|N/A
```

`observed` is either an **artifact path** (relative to the run root, e.g. `evidence/L6.3-error.png`) when a runtime capture was bound by a manifest, or **free-text** describing a manual observation. Both are legitimate; the machine seam (G6) only validates artifact-path references.

Evidence is captured, not judged. A manifest entry records that an artifact was collected at a state — it does not say the criterion passed. `pass`/`fail` is this evaluator's verdict against `required` vs `observed`; a screenshot can prove a criterion false. Three ledgers, each one authority: `spec` L6 names **what to prove**; the manifest records **what happened**; this ledger decides **what it means**. Providers produce artifacts; the manifest binds them to criteria; the evaluator decides.

For implemented UI, visible-state proof is a rendered inspection at the declared target viewport; behavior proof is an interaction trace or automated check; code-health proof is the relevant available test, type/lint, or affected build result. Planning-only proof is declaration coverage and must not claim a render or test occurred. Non-L6 declaration checks may be supporting observations or findings; they do not enter the machine ledger.

**Done when:** every bound row was considered; every L6 criterion has exactly one non-empty `criterion / required / observed / result` row keyed as `L6.<n>`; results use only `pass|fail|blocked|N/A`; unavailable required proof is `blocked`, not skipped.

### 3. Emit point-back findings

```text
issue:    <observable>
source:   <declaration>
fix:      <next edit>
severity: high (blocking)|high|med|low
```

Order: **blocking** first (broken L5/L6, unsafe dangerous ops, removed focus rings), then polish.

**Done when:** every finding has all four fields; no “generally improve the design” lines.

### 4. Verdict

- Emit exactly one `## Verdict` section containing exactly one anchored verdict: `Pass` or `Recirculate`.
- **Pass:** zero blocking; every L6 criterion has exactly one evidence row; every required evidence row passes (every evidence result is `pass`); token gaps are logged or fixed.
- **Recirculate:** each blocking `source` names the step/declaration to reopen in design-playbook; `fail` or `blocked` evidence remains visible.

For a repaired blocker, record exactly one closure line whose issue text is identical to the finding:

```text
- closes: <exact issue value> -> recirculate -> fix -> re-eval -> 0 blocking
```

**Done when:** the explicit verdict is structurally unique; blocking sources are non-empty; every blocking finding has exactly one matching closure before `Pass`. A blocking finding cannot be waived inside a Pass artifact. Without a user in the loop, blocking findings remain in recirculate and the run requests a decision. only after an explicit user decision that updates the owning declaration or severity — recorded against the user's statement or decision record — may the evaluator re-evaluate; the final Pass artifact contains no blocking severity.

The artifact shape behind this verdict is machine-checkable: `scripts/validate_run.py` gates L1-L6, ordered `Given -> When -> Then` in every top-level L6 item, one non-empty four-field evidence row per `L6.<n>`, allowed evidence results, all-pass evidence for `Pass`, four non-empty finding fields, one explicit verdict, and one exact issue-linked closure per blocking finding. These checks are the completion criteria above, not extra prose.

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
