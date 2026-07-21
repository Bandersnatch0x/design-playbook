---
description: Dogfood Design I/O once; log process gaps only
---

**Dogfood** - throwaway run. Keep the process verdict; delete or ignore generated UI unless user says keep.

1. Confirm phase >= dogfood in `.scratch/design-playbook-v0/phase.md` (if still grill, warn and prefer `/product-grill`).
2. Run skill **design-playbook** (namespaced `/design-playbook:design-io` once installed, or from `packages/design-playbook/skills/`) on the user ask below.
3. Score process only - six gates:

| Gate | Pass? |
| --- | --- |
| L5/L6 present before pretty UI | |
| Decision report before code | |
| Point-back evaluator findings | |
| No skip of Done when | |
| Generalizes (not hardcoded to one scene) | |
| Recirculate closure (blocking -> fix -> re-eval -> 0 blocking, or accepted) | |
| Run artifact index shown (spec/plan/decision/preview?/fill/evidence?/point-back paths) | |

4. Append log from the template at `.scratch/design-playbook-v0/dogfood/_template.md` to `.scratch/design-playbook-v0/dogfood/YYYY-MM-DD-HHmm.md`; fill gates + any skill fix suggestions (completion criteria / pointers only). The log must include the same **run artifact index** (absolute or run-root-relative paths) that step 9 of the design-playbook skill requires in chat.
5. Do not expand product scope. Skill text edits -> `/writing-great-skills` discipline.

Ask:
$ARGUMENTS
