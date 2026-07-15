---
name: design-playbook
description: Design I/O for product UI. Use when building a page/dashboard/list/settings UI from a short ask, fixing empty/error/permission gaps, or recirculating a failed design review. Invokes ux-spec, ui-picker, craft-guard, native-craft, ui-evaluator.
---

# design-playbook

**Design I/O** — same process every run: inject **declarations** (what good is), run **contracts** (how work enters the pipeline), **recirculate** failures to the declaration that owns them.

Not a style library. For palettes/type catalogs use other packs; here the product pipeline and acceptance are the product.

## Steps

Do in order. Do not code a pretty shell until the active step’s completion criterion is met.

### 1. Plan → `ux-spec`

Invoke **ux-spec**. Produce six-layer `spec.md`.

**Done when:** L1–L6 are written; L5 (empty/loading/error/permission) and L6 (checkable acceptance) have substantive entries, not “show loading”.

### 2. Shell → `ui-picker`

Invoke **ui-picker**. Map scene → template + component semantics. Read its `references/` only as that skill directs.

**Done when:** a short decision report names template, key components, and risks; coding has not started before that report exists.

### 3. Fill

Implement structure from the decision report + `spec`. Prefer project tokens: visual values via `var(--*)`; missing tokens → `gaps.log` (or project equivalent), not raw hex/px/ms.

If a reused host component conflicts with spec L5, record the conflict and recirculate to `spec` via the authoritative map in `ui-evaluator` before choosing a minimal patch or explicit acceptance.

Load on demand (only if the fill needs them):

- domain / risk / sensitive fields → `ui-picker/references/domain.md`
- token roles / gaps → `ui-picker/references/design.md`
- component pairs → `ui-picker/references/components.md`

**Done when:** with a codebase — main flow renders and every L5 state named in the spec has a concrete UI path (not a blank region); planning-only — every L5 state has a named concrete UI landing, no blank region.

### 4. Craft → `craft-guard`

Invoke **craft-guard**. Apply loading tiers, motion purpose, hierarchy, CJK type.

**Done when:** every wait/fail path matches craft loading tiers; every animation states its purpose; brand emphasis stays within craft budget.

### 5. Accept → `ui-evaluator`

Invoke **ui-evaluator**. Issues must **point back** to a declaration.

**Done when:** report lists findings as `issue / source / fix / severity`; the authoritative verdict completion criterion in `ui-evaluator` is met.

## Recirculate

When a finding has no owner or you need the observable -> declaration routing, use the **authoritative recirculate map in `ui-evaluator`** (do not duplicate it here). Fix only the owning layer, then resume from the step that consumes it.

## Contracts on this pipeline

| Contract | Skill |
| --- | --- |
| Write the functional declaration | `ux-spec` |
| Choose shell + component meaning | `ui-picker` |
| Craft / feedback quality | `craft-guard` |
| Native-feel desktop declaration (render seam + conventions) | `native-craft` |
| Acceptance + point-back critique | `ui-evaluator` |

Slash (installed plugin, namespaced): `/design-playbook:design-io` · `/design-playbook:ux-spec` · `/design-playbook:ui-review`.
With `claude --plugin-dir` the same command files apply under the plugin namespace.
