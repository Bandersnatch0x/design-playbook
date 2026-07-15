# Research 08 — Multi-skill plugin workflow patterns

Sources sampled:

- [Anthropic skills repo](https://github.com/anthropics/skills) (catalog of many single-purpose skills, e.g. `frontend-design`)
- [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) (large UI plugin; many skills under `.claude/skills/`)
- [Create plugins](https://code.claude.com/docs/en/plugins) (plugin vs standalone; namespacing)
- writing-great-skills vocabulary (predictability, model- vs user-invoked, progressive disclosure, completion criteria) — local skill norms

## Patterns observed

### 1. One plugin, many skills (surface area)

- **Anthropic public skills**: mostly **one skill = one folder = one SKILL.md**; each is a focused ability (e.g. frontend-design = aesthetic guidance). Discovery via description triggers.
- **ui-ux-pro-max**: **one product plugin** exposing **many skill folders** (ui-ux-pro-max, design-system, brand, design, …). Heavy skills pair **SKILL.md + data/scripts/references** (progressive load of bulk).

### 2. Orchestrator vs leaf skills

- Pro Max flagship skill is a **broad description** (“use when designing/building/reviewing UI…”) that pulls the user into a system; sibling skills specialize (brand, slides, banner).
- Anthropic frontend-design has **no multi-step orchestrator** — pure **reference/process guidance** in one file (design lead persona, anti-default aesthetics).

### 3. Model-invoked by default

- Official plugin skills are model-invoked when they have a **description** (auto-selected by task).
- `disable-model-invocation: true` used for **user-only** slash-style skills (plugin quickstart hello example).
- Pattern: **pipeline steps that other skills must call** stay model-invoked; **rare maintainer tools** can be user-only to save context load.

### 4. Progressive disclosure

- Fat plugins put bulk in `references/`, `data/`, scripts — SKILL.md stays the **ladder top** (when to apply, priority checks, pointers).
- Anthropic frontend-design keeps almost everything in-body (single-skill, all reference) — fine when the whole skill is one peer-set of rules.

### 5. Commands vs skills

- Docs: new multi-skill work prefers `skills/`; `commands/` remain flat slash markdown.
- Plugins still ship commands for **explicit user entry** (“run full pipeline”) while skills carry reusable contracts.

### 6. Completion / predictability (quality bar)

- Strong skills state **when to apply / when to skip**, ordered process, and **done signals** (our writing-great-skills: completion criteria).
- Weak pattern: long essay without checkable gates → premature completion.

## Anti-patterns

- Putting skills under `.claude-plugin/` (invalid plugin layout).
- Shipping monorepo-only maintainer commands inside the **public** plugin surface.
- Five always-on fat descriptions with no progressive disclosure (context load fight).
- Orchestrator that re-states every leaf skill’s rules (duplication / sediment).
- Bare slash names in docs that ignore plugin namespacing after install.

## Implications for design-playbook (5-skill Design I/O)

| Our piece | Pattern fit |
| --- | --- |
| `design-playbook` orchestrator | Aligns with “flagship + leaves”; keep **steps + Done when**, pointer to leaves — don’t inline all refs |
| `ux-spec` / `ui-picker` / `craft-guard` / `ui-evaluator` | Leaf skills with distinct **leading words** and model-invoke descriptions |
| `commands/design-io` | Explicit full-pipeline entry (user-facing), namespaced |
| `examples/` | Onboarding packs; keep out of always-loaded description |
| vs Pro Max | We stay **pipeline/acceptance**, not style CSV DB (compose, don’t compete) |
| vs frontend-design | Complementary aesthetic reference skill; we don’t absorb it |

**No recommendation that changes scope** — feeds tickets 03 (surface contract) and 04 (process upgrades).
