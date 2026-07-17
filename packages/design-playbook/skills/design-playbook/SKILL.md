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
| **Success** | `spec` L6 | Observable pass/fail criteria; every top-level L6 item is `Given -> When -> Then` |
| **Evidence** | `spec` L6 + evaluator ledger | Exactly one `L6.<n>` ledger row per criterion; planning-only uses declaration coverage, implementation uses rendered states, interaction/test results, and applicable code checks |
| **Stop** | this orchestrator | Pass; smallest missing decision; unavailable required evidence or authority; repeated blocker |
| **Confirm** | this orchestrator + user decision | Any consequential action not already authorized |

Answer, review, diagnose, and plan requests end with findings or a plan. Build and fix requests continue through in-scope local edits and the most relevant available validation. Ask the smallest question only when the answer changes the goal, scope, platform, success criteria, or authority; otherwise record a conservative assumption in L1.

Pause for explicit confirmation before an external, destructive, costly, or scope-expanding action that the request did not already authorize. This includes adding a dependency, changing an API/backend/data contract, deploying or publishing, and accepting a blocking finding. When required evidence or authority is unavailable, stop with the exact blocker and the smallest next decision. If the same blocking finding survives two repair -> re-evaluate cycles without new evidence, stop recirculating and report it.

## Steps

Do in order. Data flow:

`ux-spec? → plan? → (native-craft?) → ui-picker → (preview*) → fill → craft-guard → (observe*) → ui-evaluator`

- `?` = conditional entry/route
- `*` = run only when the matching MCP tool is available (`preview_prototype` for preview, `execute_capture_plan` for observe); otherwise skip
- Do not code a pretty shell until the active step’s completion criterion is met

### 1. Entry routing

**SSOT for this decision is this skill only** (not `commands/design-io.md`).

- **Missing `spec`** (no usable six-layer `spec.md` for this run) → step **2. `ux-spec`**
- **Spec present** → step **3. plan** (do not re-run `ux-spec` unless structural conflict forces it)

### 2. `ux-spec` (when spec is missing)

Invoke **ux-spec**. Produce six-layer `spec.md`.

**Done when:** L1–L6 are written; L5 (empty/loading/error/permission) has substantive entries, not “show loading”; every top-level L6 item uses ordered `Given -> When -> Then` and names the evidence that will prove it.

Then continue to **3. plan**.

### 3. plan (pipeline step — pure orchestration)

Not a run-contract control and **not** a machine gate. Does not become Goal / Success / Evidence / Stop / Confirm SSOT.

Write a light handoff at `.scratch/<run>/plan.md` (required on disk). Minimum three blocks:

1. **本次 run 范围** — pointers to L2 / scenes / non-goals (do not copy L1–L6 wholesale)
2. **用户描述 → spec 映射** — which L1/L2/L6 this ask touches; unmapped items → conservative assumptions
3. **ui-picker 输入包** — scene hints, constraints, explicit exclusions

**禁止:** paste the full spec; pre-write a decision report inside plan.

**描述 × spec 分轨:**

- **Structural conflict** (L1 outcome, L6 criteria, platform/permission/data contract, overturned non-goal) → stop; revise `ux-spec` or user Confirm of an exception recorded in plan
- **Presentation preference** (scene density, region weight, component role preference without L6 change) → put in the ui-picker input pack; `ui-picker` decides
- **Unmapped description** → mapping table as conservative assumption; do not silently edit L1

**Done when:** `plan.md` exists with the three blocks; ui-picker can consume the input pack without re-deriving scope from chat.

### 4. Shell → conditional `native-craft` → `ui-picker`

Native desktop order: `ux-spec` → `native-craft` → `ui-picker` → `fill` → `craft-guard` → `ui-evaluator`. (Conditional entry `?` and optional adapters `preview*`/`observe*` are shown in the full sequence above, step 0.)

- Invoke **native-craft** only for an explicit native-desktop target or a request for native-feel. Web and mobile Web skip `native-craft`; a Web UI that merely resembles a desktop admin tool is still Web.
- If the target platform is unclear, ask once before choosing the route. Do not assume native desktop.
- For native desktop, require the native decision gate and render-surface seam before invoking **ui-picker**. If `native-craft` cannot load or does not produce them, stop and report what is missing; do not silently choose a Web shell.
- Pass the decision gate and seam to **ui-picker** as required shell context. The caller does not reconstruct or reinterpret them.

Invoke **ui-picker**. Map scene → template + component semantics. Read its `references/` only as that skill directs.

**Done when:** a short decision report names template, key components, and risks; coding has not started before that report exists. For native desktop, it also consumes the declared render-surface seam.

`ui-picker` **stops at the decision report** — it has no preview step.

### 5. preview* (optional external MCP adapter)

After the decision report exists, probe MCP `tools/list` for **`preview_prototype`**.

- **Absent** → skip preview; go to Fill (current behavior). No preview artifacts required.
- **Present** → run the preview loop in this orchestrator (not inside `ui-picker`):
  1. Host agent generates a disposable prototype HTML (structure-semantics floor: readable scene, named template regions, key component roles as placeholders). Path under `.scratch/<run>/preview/round-{n}.html`.
  2. Call `preview_prototype` with `path` (preferred) or `html`, plus `summary`, `round`, `report_ref` (current decision report), optional `options`.
  3. Adapter shows the prototype, collects feedback, writes confirm/log under `.scratch/<run>/preview/`.
  4. On “需要修改”: append feedback to `preview/log.md`, revise the decision report in place (mark round), generate next prototype; **same blocker two repair rounds without new evidence → stop the loop and report**.
  5. On confirmed: proceed to Fill only with the confirmed decision report (+ plan pointers).

**Native desktop:** still run Web preview when the adapter exists; coverage is **render-surface seam and above** only. Note that limitation once in `preview/log.md`. Do not skip preview solely because the route is native (skip only when the adapter is missing).

**Hard boundary:** never copy `preview/round-*.html`, preview-only assets, or fake data shells into the Fill source tree. Fill consumes report semantics, not prototype files.

**Done when:** either preview was skipped (no adapter), or a `confirm-round-*.json` with `confirmed: true` matches the current decision report (G5 when `validate_run.py` is given `--preview-dir` / `--decision-report`).

### 6. Fill

Implement structure from the decision report + `spec`. Prefer project tokens: visual values via `var(--*)`; missing tokens → `gaps.log` (or project equivalent), not raw hex/px/ms.

If a reused host component conflicts with spec L5, record the conflict and recirculate to `spec` via the authoritative map in `ui-evaluator` before choosing a minimal patch or explicit acceptance.

Load on demand (only if the fill needs them):

- domain / risk / sensitive fields → `ui-picker/references/domain.md`
- token roles / gaps → `ui-picker/references/design.md`
- component pairs → `ui-picker/references/components.md`

**Done when:** with a codebase — main flow renders and every L5 state named in the spec has a concrete UI path (not a blank region); planning-only — every L5 state has a named concrete UI landing, no blank region.

### 7. Craft → `craft-guard`

Invoke **craft-guard**. Apply loading tiers, motion purpose, hierarchy, CJK type. For native desktop, `craft-guard` owns shared UI above the render-surface seam and defers to `native-craft` below it. If a finding crosses the seam, split it into separate point-backs to the owning declarations.

**Done when:** every wait/fail path matches craft loading tiers; every animation states its purpose; brand emphasis stays within craft budget.

### 8. observe* (optional external MCP adapter)

After craft, probe MCP `tools/list` for **`execute_capture_plan`**.

- **Absent** → skip; `ui-evaluator` ledger `observed` stays free-text (current behavior). G6 not triggered.
- **Present** → for each L6 criterion whose proof is a runtime state, run the evidence loop in this orchestrator (not inside any skill):
  1. **Derive** a capture plan from L6 `Given -> When -> Then` (in memory, not on disk): `Given`/`When` → `state` + `actions`; `Then` → required proof (already in the ledger `required` field). Do not add or remove verification intent; L6 wins on conflict.
  2. **Execute**: call `execute_capture_plan({url, type, state, actions, artifact_path})`. The provider returns `{artifact, observed_state, result, error}` and never sees the criterion.
  3. **Bind**: append a manifest entry to `.scratch/<run>/evidence/manifest.jsonl` with the criterion ref + embedded capture snapshot + artifact + `observed_state` + `result` (`captured`|`failed`) + `ts`. The orchestrator owns the manifest; the provider never writes it.
  4. **Manual provider**: when no ecosystem provider is present but a human operates + screenshots to `artifact_path`, write the same-format manifest entry (`capture.provider: "manual"`).
- v1 capture types: `screenshot` / `a11y tree` / `interaction trace`.

Evidence is captured, not judged: a manifest entry records that an artifact was collected at a state — it does not say the criterion passed. `pass`/`fail` is the evaluator's verdict (step 9) against `required` vs `observed`; a screenshot can prove a criterion false.

**Done when:** either observe was skipped (no provider, ledger `observed` free-text), or each runtime-proven criterion has a manifest entry whose artifact exists (G6 when `validate_run.py` is given `--evidence-dir`).

### 9. Accept → `ui-evaluator`

Invoke **ui-evaluator**. Issues must **point back** to a declaration.

**Done when:** the report includes the criterion-shaped evidence ledger (`criterion / required / observed / result`) and findings as `issue / source / fix / severity`; the authoritative verdict completion criterion in `ui-evaluator` is met.

Machine seam (optional local check): `python scripts/validate_run.py <spec.md> <point-back.md> [--preview-dir <preview/>] [--decision-report <report>] [--evidence-dir <evidence/>] [--run-root <run>]`.

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

`plan`, `preview*`, and `observe*` are orchestrator steps (plus optional external MCPs for preview and observe), not rows in this table.

Slash (installed plugin, namespaced): `/design-playbook:design-io` · `/design-playbook:ux-spec` · `/design-playbook:ui-review`.
With `claude --plugin-dir` the same command files apply under the plugin namespace.
