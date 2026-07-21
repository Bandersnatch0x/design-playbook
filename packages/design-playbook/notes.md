# design-playbook — decision notes

Maintainer-facing records that are not ADRs (no architectural fork) but must stay visible next to the package.

---

## 2026-07-21 — Capture≠judge dual placement (orchestrator §8 vs ui-evaluator)

| field | value |
| --- | --- |
| **Context** | Skill Predictability Loop (writing-great-skills) flagged near-verbatim “Evidence is captured, not judged” in both `skills/design-playbook/SKILL.md` (observe / §8) and `skills/ui-evaluator/SKILL.md` (step 2). |
| **Options** | **A** Keep full dual copy · **B** Delete from orchestrator entirely · **C** Keep leading token at both seams; meaning/authority body SSOT in `ui-evaluator` only |
| **Decision** | **Option C** |
| **Rationale** | Bind phrase at both seams so agents don’t invent “manifest = pass”. Authority model (three ledgers) must not fork — evaluator step 2 is SSOT. Orchestrator keeps the token + one-line bind + pointer; no second full essay. |
| **Applied** | `skills/design-playbook/SKILL.md` observe Done-when block: token retained; full three-ledger prose replaced by pointer to `ui-evaluator` step 2. `ui-evaluator` step 2 unchanged as SSOT. |
| **Non-goals** | No G5/G6 protocol change; no recirculate-map edit; no MCP behavior change. |
| **Source** | Loop dispatch `task_495f637fbd45` / `ctx_fce2f0f098f5`; human confirm 2026-07-21. |

---

## Related loop artifacts (not package SSOT)

- Queue / audits: `.scratch/skill-predictability/` (repo scratch; may be local-only)
