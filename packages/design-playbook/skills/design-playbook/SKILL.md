---
name: design-playbook
description: Orchestrate outcome-first Design I/O for product UI. Use when building or revising a page, dashboard, list, or settings surface from a short ask, or recirculating a failed design review through declarations and evidence.
---

# design-playbook

**Design I/O** — same process every run: inject **declarations** (what good is), run **contracts** (how work enters the pipeline), **recirculate** failures to the declaration that owns them.

Not a style library. For palettes/type catalogs use other packs; here the product pipeline and acceptance are the product.

## Run contract

Keep each control in one authoritative place:

| Control | Single source | Required content |
| --- | --- | --- |
| **Goal** | `spec` L1 | User-visible outcome, target user and scene, non-goals |
| **Success** | `spec` L6 | Observable pass/fail criteria |
| **Evidence** | `spec` L6 + evaluator ledger | Proof for every criterion; planning-only uses declaration coverage, implementation uses rendered states, interaction/test results, and applicable code checks |
| **Stop** | this orchestrator | Pass; smallest missing decision; unavailable required evidence or authority; repeated blocker |
| **Confirm** | this orchestrator + user decision | Any consequential action not already authorized |

Answer, review, diagnose, and plan requests end with findings or a plan. Build and fix requests continue through in-scope local edits and the most relevant available validation. Ask the smallest question only when the answer changes the goal, scope, platform, success criteria, or authority; otherwise record a conservative assumption in L1.

Pause for explicit confirmation before an external, destructive, costly, or scope-expanding action that the request did not already authorize. This includes adding a dependency, changing an API/backend/data contract, deploying or publishing, and accepting a blocking finding. When required evidence or authority is unavailable, stop with the exact blocker and the smallest next decision. If the same blocking finding survives two repair -> re-evaluate cycles without new evidence, stop recirculating and report it.

## Steps

Do in order. Do not code a pretty shell until the active step’s completion criterion is met.

### 1. Plan → `ux-spec`

Invoke **ux-spec**. Produce six-layer `spec.md`.

**Done when:** L1–L6 are written; L5 (empty/loading/error/permission) has substantive entries, not “show loading”; each L6 criterion is checkable and names the evidence that will prove it.

### 2. Shell → conditional `native-craft` → `ui-picker`

Native desktop order: `ux-spec` → `native-craft` → `ui-picker` → `fill` → `craft-guard` → `ui-evaluator`.

- Invoke **native-craft** only for an explicit native-desktop target or a request for native-feel. Web and mobile Web skip `native-craft`; a Web UI that merely resembles a desktop admin tool is still Web.
- If the target platform is unclear, ask once before choosing the route. Do not assume native desktop.
- For native desktop, require the native decision gate and render-surface seam before invoking **ui-picker**. If `native-craft` cannot load or does not produce them, stop and report what is missing; do not silently choose a Web shell.
- Pass the decision gate and seam to **ui-picker** as required shell context. The caller does not reconstruct or reinterpret them.

Invoke **ui-picker**. Map scene → template + component semantics. Read its `references/` only as that skill directs.

**Done when:** a short decision report names template, key components, and risks; coding has not started before that report exists. For native desktop, it also consumes the declared render-surface seam.

### 3. Fill

Implement structure from the decision report + `spec`. Prefer project tokens: visual values via `var(--*)`; missing tokens → `gaps.log` (or project equivalent), not raw hex/px/ms.

If a reused host component conflicts with spec L5, record the conflict and recirculate to `spec` via the authoritative map in `ui-evaluator` before choosing a minimal patch or explicit acceptance.

Load on demand (only if the fill needs them):

- domain / risk / sensitive fields → `ui-picker/references/domain.md`
- token roles / gaps → `ui-picker/references/design.md`
- component pairs → `ui-picker/references/components.md`

**Done when:** with a codebase — main flow renders and every L5 state named in the spec has a concrete UI path (not a blank region); planning-only — every L5 state has a named concrete UI landing, no blank region.

### 4. Craft → `craft-guard`

Invoke **craft-guard**. Apply loading tiers, motion purpose, hierarchy, CJK type. For native desktop, `craft-guard` owns shared UI above the render-surface seam and defers to `native-craft` below it. If a finding crosses the seam, split it into separate point-backs to the owning declarations.

**Done when:** every wait/fail path matches craft loading tiers; every animation states its purpose; brand emphasis stays within craft budget.

### 5. Accept → `ui-evaluator`

Invoke **ui-evaluator**. Issues must **point back** to a declaration.

**Done when:** the report includes the evidence ledger and findings as `issue / source / fix / severity`; the authoritative verdict completion criterion in `ui-evaluator` is met.

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
