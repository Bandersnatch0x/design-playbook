---
name: design-playbook
description: Route and orchestrate outcome-first product UI work. Use for answer, review, diagnosis, plan, prototype, build, or fix requests about pages, dashboards, lists, or settings. Also use to recirculate failed design review through declarations and evidence.
---

# design-playbook

Design I/O uses the same process every run.
Inject declarations (what good is), run contracts (how work enters the pipeline), and recirculate failures to the declaration that owns them.

Not a style library. For palettes and type catalogs use other packs. Here the product pipeline and acceptance are the product.

## Plugin root (`<plugin>`)

`<plugin>` in every command below means the loaded plugin package root.
Confirm it deterministically before the first `<plugin>` command, the skill's base directory is `<plugin>/skills/design-playbook`, so resolve from it and verify the
package marker:

```bash
python -c "import json,sys; from pathlib import Path; p=Path(sys.argv[1]).resolve().parents[1]; print('plugin root:', p); print('version:', json.loads((p/'.claude-plugin'/'plugin.json').read_text(encoding='utf-8'))['version'])" "<skill base directory>"
```

An empty `$CLAUDE_PLUGIN_ROOT` (dev `--plugin-dir` loads) is expected.
This probe does not depend on it.
If the marker read fails, the loaded tree is not the packaged plugin, stop and report the path actually in use.

## Run contract

Keep each control in one authoritative place:

| Control | Single source | Required content |
| --- | --- | --- |
| **Goal** | `spec` L1 | User-visible outcome, target user and scene, non-goals |
| **Success** | `spec` L6 | Observable pass or fail criteria. Every top-level L6 item is `Given, then When, then Then` |
| **Evidence** | `spec` L6 + evaluator ledger | Exactly one `L6.<n>` ledger row per criterion. Planning-only uses declaration coverage, implementation uses rendered states, interaction and test results, and applicable code checks |
| **Stop** | this orchestrator | Pass. Smallest missing decision. Unavailable required evidence or authority. Repeated blocker |
| **Confirm** | this orchestrator + user decision | Any consequential action not already authorized |
| Tier | `plan.md` run-profile block | Tier (P1/P2/P3) + grading checklist + skip list + upgrade events |

## Run profile (tier grading)

Apply this section only after entry routing returns `design-run`; `no-run`
creates no profile or run artifacts.

Project the router's initial tier and criteria once, up front (LR1).
Three tiers share one state machine and one artifact set, the tier only changes how deep each step goes:

- P1 point-fix, bind fast path + assumed acknowledgement. No design-decision entry or shaping session; R2 row-level spec additions remain allowed.
- P2 standard, full `ux-spec` shaping session (S0-S6, G9), R-tier and C-tier design decisions, and standard evidence and review obligations.
- P3 full, full declaration, alternative, interaction, and applicability coverage.

The executable router proposes the initial grade and the user confirms it once (may fold into the request reply).
Upgrade is automatic the moment a correction signal appears (R1 finding, structural R2, cross-layer blocking, E-tier judgment).
Record the upgrade event in the run-profile block and walk the added steps.
Downgrade requires the user (over-compliance already performed is kept).
Write the block into `plan.md` as a structured field block (`tier: P1|P2|P3`, grading checklist, `confirmed_by: user + <ts>`, skip list with one-line reasons,
upgrade events).
The profile block is mandatory for every run.
Body-omission conditions and handoff completion are defined only in step **4. plan**.
Every skipped step keeps the one-line skip narration rule below.
Audit-preference tier waivers follow the SSOT section below.

On a `design-run`, ask the smallest question only when the answer changes the goal, scope, platform, success criteria, or authority.
Otherwise record a conservative assumption in L1.
Whether a request is `no-run` or `design-run` is only the router decision from step 1, including durable review, diagnosis, or plan work.

Pause for explicit confirmation before an external, destructive, costly, or scope-expanding action that the request did not already authorize.
This includes adding a dependency, changing an API, backend, or data contract, deploying or publishing, and accepting a blocking finding.
When required evidence or authority is unavailable, stop with the exact blocker and the smallest next decision.
If the same blocking finding survives two repair and re-evaluate cycles without new evidence, stop recirculating and report it.

## Audit preferences (ADR-0033)

The audit and acceptance stages, `craft-guard`, `observe*`, `ui-evaluator`, are user-selectable.
Fill and the preview confirmation (ADR-0008 floor) never are.
Preferences are execution trimming after routing: `run_profile.py route` receives no preference input and this section never feeds it.

Read (one deep module, consume its output, never reconstruct its precedence):

```
python <plugin>/scripts/audit_preferences.py plan --repo-root <target-repo> [--declaration '{"craft_guard": false}']
```

The printed payload is the only trimming authority: `stages.<stage>.runs` decides whether the stage executes, `source` (`default` / `local` /
`repo` / `run`) narrates where the choice came from, and `asked` projects the merged asked bit.
Each `invalid_files` entry names one corrupt layer that was treated as absent; decide whether to ask from `asked`, since another valid layer may still preserve `asked: true`.
A run declaration (this run's user statement, natural language mapped to the three booleans) is passed via `--declaration` and outranks both preference files.

First ask (folded into tier confirmation): when the payload reports `asked: false`, ask the one-time audit-scope question.
Merge it into the tier-confirmation exchange above, so the run has one interruption, not two.
Collect the `craft_guard` / `observe` / `ui_evaluator` choices together with the tier confirmation.
They become the run declaration for this run.
Repository values are team-authored input, not proof of this user's choice.
Check whether any effective stage has `source: repo` and audit scope remains unconfirmed in this session.
If so, confirm those stored choices in the same exchange and pass the answer as the run declaration.
Never silently treat repository `asked: true` as current-user consent.

Write-back (remember the answer): persist the answered declaration through the module, `write_back(repo_root, declaration, scope=..., this_run_only=...)` from `design_playbook.scripts.audit_preferences` (bootstrap: `sys.path.insert(0, '<plugin>')`).
Scope `repo` writes `.design-playbook/preferences.yaml` (team-shared default, version-controlled).
Scope `local` writes `.design-playbook/preferences.local.yaml` and automatically ensures `.design-playbook/preferences.local.yaml` is listed in the target repository's `.gitignore`.
When the user says "this run only", pass `this_run_only=True`: the choice applies to this run but is not persisted, and the asked bit is still consumed.
The write-back also sets the asked bit, so the first-use question is not repeated.
Repository-sourced choices still receive the per-session confirmation above.

Trim + skip-list recording: for every stage whose `runs` is false, skip the step and record it in the run-profile skip list.
Give a one-line reason naming the source, for example `craft-guard: skipped by user audit preference (source: run)`.
Record every skip: silent skips are illegal, and the one-line skip narration rule still applies.
The run artifacts carry a limitation statement naming what was not audited.
Never present absence of evidence as evidence.

Skeleton point-back (`ui-evaluator` skipped): `point-back.md` is a machine hard dependency, so a skipped audit still emits one.
Generate it with the module's `skeleton_pointback(spec_text)`, marked `audited: false` with a fixed limitation sentence, for example:

```
python -c "import sys; sys.path.insert(0, '<plugin>'); from pathlib import Path; from design_playbook.scripts.audit_preferences import skeleton_pointback; run = Path('.scratch/<run>'); (run / 'point-back.md').write_text(skeleton_pointback((run / 'spec.md').read_text(encoding='utf-8')), encoding='utf-8')"
```

Never edit out the `audited: false` marker or upgrade the skeleton's verdict: `validate_run --strict` / `--require-evidence` / `--require-coverage` reject skeleton runs,
`run_status` projects *not audited*, and `aggregate_runs` surfaces them as unaudited (ADR-0033 D12).
Optionality is a convenience for honest users, not a forgery channel.

Tier-obligation waiver: an explicit user skip of `craft-guard` authorizes the corresponding P2/P3 obligation downgrade (full-catalog evaluation,
G11 sampling matrix) automatically.
The waiver is recorded in the skip list (ADR-0033 D8).
The "downgrade needs the user" rule guards against agent self-demotion, the user's own declaration is the authorization.

## Steps

Stage registry: packaged `scripts/stages.py` (`STAGES`). Consistency check: `tests/test_stages_registry.py`.

Do in order. Data flow:

`design-baseline? → reference-intake? → ux-spec? → plan? → (native-craft?) → ui-picker → (preview*) → fill → craft-guard → (observe*) → ui-evaluator`

- `?` = conditional entry and route
- `*` = run only when the matching MCP tool is available (`preview_prototype` for preview, `execute_capture_plan` for observe). Otherwise skip
- `craft-guard`, `observe*`, and `ui-evaluator` are also user-selectable via Audit preferences (ADR-0033). Trimming there never changes this order
- When you skip a step, say so in one line, step name + reason + how to enable, with the gate label when one applies.
  Matters most for `preview*`/`observe*` adapter absence, e.g.
  `preview*: adapter absent, skipped (G5 not triggered; enable via packages/design-playbook/mcp/preview/ or host MCP)`.
  Other conditional skips may use the same shape.
  Entry lines are optional (keep output lean).
  Narration only, not a run-contract control.
- Do not code a pretty shell until the active step’s completion criterion is met

### 1. Entry routing

Executable routing authority:
`<plugin>/scripts/run_profile.py route`. This skill owns fact
normalization and orchestration; `commands/design-io.md` only invokes it.

Normalize the request and repository facts, call `run_profile.py route`, and
keep its returned `mode`, tier, criteria, and prerequisite flags as the only
initial route decision.

```text
python <plugin>/scripts/run_profile.py route \
  --intent fix --consequence local --existing-product --has-references
```

`--intent` and `--consequence` are required. The rest of the facts are the
boolean and count flags listed by `run_profile.py route --help`. The router takes
normalized facts only, it has no repository-path or request-text argument, so
do not invent one.

- `no-run`: respond directly. Do not create `.scratch/<run>/`, `plan.md`, or a
  run-profile.
  A vision-capable host may inspect an attached image directly.
  A text-only host records the metadata and states once that visual inspection is unavailable.
  If the user supplied only an image without accompanying text, ask for a short written description before finishing.
  Continue with that description.
  Stating
  the limitation once is not a stop condition when text material is missing.
  Neither path copies the temporary image.
- `design-run`: project the returned tier and criteria into the existing v1
  run-profile, then satisfy the independently returned prerequisites.

Treat a router error as a stop and correct the normalized facts. Do not
reconstruct its decision table in prose. The router does not decide later
preview and observe adapter availability or evaluator verdicts.

- If `requires_baseline`, continue to step 1A. `design-baseline`. Otherwise skip it.
- If `requires_reference_contract`, continue to step 2. `reference-intake`. Otherwise skip it.
- If `requires_spec`, continue to step 3. `ux-spec`. Otherwise continue to step 4. plan.

**Done when:** `run_profile.py route` returned a decision that this skill consumed without reconstructing its table; `no-run` created no `.scratch/<run>/`
artifacts; `design-run` projected the returned tier, criteria, and prerequisite flags.

### 1A. `design-baseline` (when required)

Invoke design-baseline before reference intake or specification work.
Call the deep module `prepare`, then `confirm` as needed: this run's user confirms or waives, a waiver is never carried over from an earlier run or another agent, and that skill owns the rule.
Immediately before Fill call `verify`.
Discover and validate project `DESIGN.md`.
If missing or incomplete, generate only run-local `DESIGN.draft.md` + `evidence.json` from first-party UI evidence and wait for confirmation before a
durable write.

Gate artifact is only `.scratch/<run>/design-baseline/state.json` (`schema: design-baseline/v1`).
A valid existing baseline becomes `status: ready` with `decision.kind: existing`.
A generated draft requires `confirm(..., "accept")` (`ready` + `accepted`) or explicit `confirm(..., "waive", reason=...)` (`waived`).
`needs_confirmation` and `ambiguous` block Fill.
A draft alone is not authority.

**Done when:** design-baseline's own completion criteria hold (that skill is SSOT).
Smoke: `state.json` exists.
Candidate conflicts and stale source hashes are exposed by prepare and verify.
Status is `ready` or `waived`.
No valid baseline was silently replaced.

### 2. `reference-intake` (when `requires_reference_contract`)

Invoke reference-intake. Produce `.scratch/<run>/reference/contract.md` + `reference/manifest.json` (ADR-0011).

**Done when:** reference-intake's own completion criteria hold (that skill is SSOT).
Smoke: sources inventoried.
Observed vs inferred labeled; Keep, Change, and Do not copy present for product-analogy, third-party URL, and third-party screenshot or design.
License and brand risks recorded.
Does not write `spec.md` or a decision report.

Then continue to 3. `ux-spec` (or 4. plan when spec already exists).

### 3. `ux-spec` (when spec is missing)

Invoke ux-spec.
Produce six-layer `spec.md` with the L2-L5 structured field blocks.
For P2/P3 runs the skill runs as a shaping session (S0-S6 with CP batches; append-only artifacts under `.scratch/<run>/shaping/`, `shaping-log.jsonl` + derived
`queue.json`; G9 gates the session exit).
P1 runs skip the session and use the bind fast path.
When `.scratch/<run>/reference/contract.md` exists, ux-spec must read it first (functional constraints, non-goals, always, ask, and never), do not wait for plan.

**Done when:** ux-spec's own completion criteria hold (that skill is SSOT).
Smoke: L1–L6 present; L5 substantive, not "show loading".
Every top-level L6 item uses ordered `Given, then When, then Then`, names its evidence, and names the capture seed where the proof is a runtime state.
Reference constraints folded when a contract exists.

Then continue to 4. plan.

### 4. plan (pipeline step — pure orchestration)

Not a run-contract control beyond the Tier row and **not** a machine gate. Does not become Goal / Success / Evidence / Stop / Confirm SSOT.

Write a light handoff at `.scratch/<run>/plan.md` (required on disk).
It must open with the `run-profile` structured block defined in *Run profile* above, even when the body is omitted.

**Body omission (all conditions required):**

- The current on-disk artifacts already supply all three handoff inputs below for this request and current spec, with concrete file and section pointers.
  Chat history alone is not a handoff.
- The description × spec checks below leave no unresolved structural conflict, unmapped item, or presentation input left to record.
- The run-profile skip list records `plan` with a one-line reason explicitly saying only the body is omitted, plus the input pointers.
  Narrate this skip using the Steps rule.

Tier alone does not authorize omission.
Recheck these conditions when scope, spec, reference constraints, or tier changes.
If any condition no longer holds, write or update the full handoff.
Keep an existing body rather than deleting work already performed.

**Full handoff:** otherwise write these three body blocks:

1. **This run's scope**, pointers to L2 / scenes / non-goals (do not copy L1–L6 wholesale)
2. **User description → spec mapping**, which L1/L2/L6 this ask touches. Unmapped items then conservative assumptions
3. **ui-picker input pack**, scene hints, constraints, explicit exclusions

**Reference handoff (both paths):** when `.scratch/<run>/reference/contract.md` exists, include its path in the body or omission skip entry (do not paste the full contract).
Fold its functional constraints into the description-to-spec map and its visual cues/exclusions into the ui-picker input pack.
This applies whether the inputs are written here or reached through the omission pointers.
An unconsumed reference contract does not qualify for body omission.

Prohibited: paste the full spec. Pre-write a decision report inside plan.

Description × spec branching:

- For a structural conflict (L1 outcome, L6 criteria, platform, permission, or data contract, overturned non-goal) → stop; revise `ux-spec` or user Confirm of an exception recorded in plan
- For a presentation preference (scene density, region weight, component role preference without L6 change), put it in the ui-picker input pack;
  `ui-picker` decides
- Record an unmapped description in the mapping table as a conservative assumption. Do not silently edit L1

**Done when:** `plan.md` exists with the required opening `run-profile` block, the reference handoff holds when applicable, and one of these paths is complete:

- **Full handoff:** the three blocks are present and the description × spec branches have been handled as above.
- **Profile-only handoff:** all body-omission conditions above hold, including the recorded reason and input pointers.

In either path, ui-picker can consume the saved input pack without re-deriving scope from chat.

### 5. Shell with conditional `native-craft`, then `ui-picker`

Native desktop order: `ux-spec` then `native-craft` then `ui-picker` then `fill` then `craft-guard` then `ui-evaluator`. (Conditional entry
`?` and optional adapters `preview*`/`observe*` are shown in the full sequence above, step 0.)

- Invoke native-craft only for an explicit native-desktop target or a request for native-feel.
  Web and mobile Web skip `native-craft`.
  A Web UI that merely resembles a desktop admin tool is still Web.
- If the target platform is unclear, ask once before choosing the route. Do not assume native desktop.
- For native desktop, require the native decision gate and render-surface seam before invoking ui-picker.
  If `native-craft` cannot load or does not produce them, stop and report what is missing.
  Do not silently choose a Web shell.
- Pass the decision gate and seam to ui-picker as required shell context. The caller does not reconstruct or reinterpret them.

Invoke ui-picker.
Map the scene to a template and component semantics.
Read its `references/` only as that skill directs.
When `.scratch/<run>/reference/contract.md` exists, pass its visual cues and exclusions (via the plan input pack, the direct path, or both) into ui-picker.

**Done when:** ui-picker's own completion criteria hold (that skill is SSOT).
Smoke: the decision report names scene, density, template, regions, components, and risks.
Coding has not started before that report exists.
For native desktop, it also consumes the declared render-surface seam.

`ui-picker` stops at the decision report, it has no preview step.

### 6. preview* (optional external MCP adapter)

After the decision report exists, probe MCP `tools/list` for `preview_prototype`.
Load operating detail only when present: [`references/load-map.md`](references/load-map.md) + [`references/preview-ops.md`](references/preview-ops.md).

- If absent, skip preview. Go to Fill. Narrate step + reason + enable path (G5 not triggered).
- If present, follow `preview-ops.md` (prototype then HITL then floor then confirm). Proceed to Fill only with `confirmed=true` and `floor_pass=true`.

Native desktop: still run Web preview when the adapter exists.
Coverage is render-surface seam and above only.
Record the limitation once in `preview/log.md`.
Do not skip preview solely because the route is native (skip only when the adapter is missing).

Hard boundary: never copy `preview/round-*.html`, preview-only assets, fake data shells, `reference/assets/`, or `reference/example.html` (or any other file under `.scratch/<run>/reference/`)
into the Fill source tree.
Fill consumes report + `spec` semantics, not prototype or reference media files.

Re-Fill signal (preview after Fill already exists): check whether a Fill surface already exists, either code under the host tree or `filled-ui.*`.
A later preview round may revise `decision-report.md`, absorbing a new round or a structural or component change.
Before observe* or ui-evaluator, re-Fill or explicitly record user acceptance that the existing Fill already matches the new report.
Do not run observe against a Fill that predates the current confirmed report.
Log the re-Fill (or acceptance) once in `preview/log.md`.

**Done when:** either preview was skipped (no adapter), or a `confirm-round-*.json` with `confirmed: true` and `floor_pass: true` matches the current decision report.
G5 applies when `validate_run.py` is given `--preview-dir` or `--decision-report`.
Run its single gate right after the confirm record lands: `python scripts/g5_preview.py .scratch/<run>/preview/`.
A confirmed record without `floor_pass` fails G5. Empty or garbage feedback is a silent false-pass that must not reach Fill.
When Fill already existed, the re-Fill signal above is satisfied.

### 7. Fill

Implement structure from the decision report + `spec` + confirmed project `DESIGN.md` when bound.
Prefer project tokens: visual values via `var(--*)`.
Record missing tokens in `gaps.log` (or project equivalent), not raw hex, px, or ms.

Hard boundary (design baseline): for existing-product UI work, do not enter Fill unless `design_baseline.verify(project_root, run_root)` succeeds with `status` `ready` (bound
path + sha256) or `waived` (non-empty reason).
A draft alone is not authority.

Hard boundary (reference): never copy `.scratch/<run>/reference/assets/`, `reference/example.html`, or third-party brand media inventoried by reference-intake into the host Fill
tree.
Honor Do not copy via report + `spec` only.

If a reused host component conflicts with spec L5, record the conflict.
Then recirculate to `spec` via the authoritative map in `ui-evaluator` before choosing a minimal patch or explicit acceptance.

Fill artifact location: the Fill surface may live in the host tree (product side) instead of the run root.
A run-root Fill lands as `filled-ui.html` + `filled-ui.md`.
When the surface lives in the host tree, register each path in `plan.md` as a `fill: <path>` field line.
Use one unfenced column-0 line per path, either run-root-relative or host-project-relative.
Fenced examples and prose blocks are never read as declarations.
`run-status` judges Fill on those declared paths and on `filled-ui.html` or `filled-ui.md` in the run root.
An out-of-run Fill surface with no registered path leaves the fill stage unchecked.

Load on demand (only if the fill needs them):

- For domain, risk, and sensitive fields, read `ui-picker/references/domain.md`
- For token roles and gaps, read `ui-picker/references/design.md`
- For component pairs, read `ui-picker/references/components.md`

**Done when:** with a codebase, main flow renders and every L5 state named in the spec has a concrete UI path (not a blank region).
Planning-only, every L5 state has a named concrete UI landing, no blank region.

### 8. Craft with `craft-guard`

When the audit-preferences plan reports `craft_guard.runs: false`, skip this step.
Record the skip-list reason using the plan payload source.
Keep the one-line skip narration and carry the waiver into the limitation statement (see *Audit preferences*).
Otherwise:

Invoke craft-guard.
Apply loading tiers, motion purpose, hierarchy, CJK type.
Craft rules live in the first-party registry (`references/rules.md`): evaluate each entry's applicability predicate (P1: touch-surface subset; P2/P3: full
catalog) and write seven-column audit rows to `.scratch/<run>/craft-guard.md`.
For native desktop, `craft-guard` owns shared UI above the render-surface seam and defers to `native-craft` below it.
If a finding crosses the seam, split it into separate point-backs to the owning declarations.

**Done when:** craft-guard's own completion criteria hold (that skill is SSOT).
Smoke: every wait and fail path maps to a loading tier.
Every animation states its purpose; L4 interactive-zone affordance resolved.
Residual issues handed to `ui-evaluator` with source `craft`.

### 9. observe* (optional external MCP adapter)

After craft, probe MCP `tools/list` for `execute_capture_plan`.

- Skipped by audit preference (`observe.runs: false` in the audit-preferences plan) then skip exactly like adapter absence.
  Narrate step + reason (`user audit preference, source: <source>`) and record it in the skip list.
- If absent, skip; `ui-evaluator` ledger `observed` stays free-text (current behavior). G6 not triggered.
- If present, for each L6 criterion whose proof is a runtime state, run the evidence loop in this orchestrator (not inside any skill):
  1. Derive a capture plan from L6 `Given, then When, then Then` (in memory, not on disk): `Given`/`When` then `state` + `actions`; `Then` then
     required proof (already in the ledger `required` field).
     Do not add or remove verification intent; L6 wins on conflict.
  2. Execute: call `execute_capture_plan` under capture contract v1 (ADR-0018): required `schemaVersion: 1`, explicit `viewport` (`width`, `height`,
     `devicePixelRatio`, `colorScheme`), plus `url`, `type`, `state`, `actions`, `artifact_path`.
     Optional static preflight before the first call (ADR-0043 narrow slice): `python "$CLAUDE_PLUGIN_ROOT/mcp/evidence/evidence_preflight.py" <plan.json>`.
     It reports error or advisory facts about required fields, action params, artifact boundary, the `file://` mirror-surface note, and
     `storage_state` path shape.
     It never calls a Provider or writes anything.
     These facts are narration, not a verdict.
     Optional `freeze` defaults to `{enabled: true, waitFonts: true, networkIdle: false}`, freeze is on by default in observe*.
     Missing or unknown schema versions fail closed with a recapture instruction.
     There is no dual-read for unversioned evidence.
     The provider returns `{artifact, observed_state, result, error, written_path, request}` and never sees the criterion.
     Prefer `written_path` (absolute) when locating the file.
     If it points outside `.scratch/<run>/`, recapture with the optional `run_root` argument (absolute run root, this call only) or fix `DESIGN_PLAYBOOK_RUN_ROOT`
     / cwd before binding.
     `artifact_path` must start with `evidence/` (e.g., `evidence/empty-state.png`, not `empty-state.png`), the provider resolves it under `<run_root>/evidence/` and refuses
     absolute paths, `..` segments, or anything that escapes that subtree (`mcp/evidence/server.py` `_resolve_artifact_path`).
     A bare filename is rejected because it would land outside the evidence subtree.
     P2/P3 viewport seed: for screenshot proof, derive one entry per name in `mcp/evidence/disclosure.py` `WEB_VIEWPORTS` (print excluded).
     P1 does not require that seed.
     Dark / 压力包 are not default seeds.
     Sidecar probe: a screenshot capture that the adapter can probe also writes `<stem>.probe.json` (`page-probe/v1`: top-level `layout` / `leaks`
     / `tapFails` / `consoleErrors` plus `layout|defects|console.measurement_status` and `measurement_error`), facts, not a judgment.
     G6 binds only `manifest.artifact` (evidence/-relative leaf, no `evidence/` prefix) to the ledger `observed` leading token (`evidence/<leaf>`).
     `probe_artifact` is not a binding key.
     When the L6 Then is a layout / leak / tap-target / console fact, the primary artifact is the probe JSON leaf.
     The originating screenshot call stays in `capture` (`type`/`url`/`state`/`actions`/`artifact_path`) and Provider
     `request` (schemaVersion, viewport, and freeze only).
     One capture may append one manifest line per criterion.
     Evaluator must read `measurement_status` on the relevant face before interpreting arrays; `blocked`/`unmeasured` is not a clean zero-hit.
     Session: optional `storage_state` is a run-root-relative Playwright JSON path kept outside `evidence/` and out of `run-handoff`.
     Record that path under `capture.storage_state` (see `mcp/evidence/capture_snapshot.py`).
     Never copy file bytes, cookies, or tokens into manifest, logs, or diagnostics.
     Preflight checks path shape only (trim then shape; no stat).
     Capture fail-closed on missing, unreadable, non-object, or nonstandard JSON.
     Path / file / expiry / unsupported blocked classes: next owner is the operator, see ui-evaluator `references/repair.md`.
     `captured` / `observed_state: ok` is not proof the declared target page was reached, require the plan's target URL and `wait_for_state`/`wait_for_selector`
     on that page.
     Login or wrong page then ledger `blocked`.
     P2/P3 mix: a fail or blocked L6×viewport pair is not covered by another viewport's pass.
     Async-init timing: the page may show a skeleton or loading state before `body[data-state]` reaches the target state.
     Include a `wait_for_state` action for that state before capture.
     A capture that lands mid-init records the loading state honestly (`observed_state: loading`), which proves the wrong criterion (dogfood 2026-08-01
     settings run).
  3. Bind (orchestrator owns the manifest; provider never writes it and never sees the criterion).
     After each successful or failed capture, immediately append one line per bound L6 criterion to `.scratch/<run>/evidence/manifest.jsonl`, do not batch-rewrite the file at
     the end.
     Rules:
     - `observed_state` / `result` / `error`: copy the provider return verbatim.
       If the provider returns `unknown`, write `unknown`, never overwrite with the requested `state` (request intent lives only under
       `capture.state`).
     - Embedded capture snapshot: store the full call parameters used (`url` including query string, `type`, `state`, `actions`,
       `artifact_path`, plus `schemaVersion`/`viewport`/`freeze` if not already in `request`) under `capture`.
       Echo the provider `request` object unchanged (contract fields only, no `request.type`).
       Omit nothing that would be needed to re-run the capture.
       Do not copy `storage_state` file bytes into the line.
     - `ts`: wall-clock of this capture's completion (ISO-8601 with an explicit UTC offset: `Z` or `+HH:MM`).
       The latest binding wins by instant, so mixed offsets order by capture time.
       A stamp without an offset names no instant and fails closed.
       Distinct captures must not share one batch timestamp.
     - Also record the criterion ref and `artifact`, the evidence/-relative leaf of the primary proof.
       Use the probe JSON leaf for layout, leak, tap, and console Then; use the png leaf for visible-state Then.
       Optional fields are `artifact_sha256`, the provider's `written_path`, and `probe_artifact` (run-root-relative, not a G6 key).
     - Method-semantics five keys are orchestrator-owned and written at this same bind. Append these fields to the entry:
       - `method`: nine-value enum `static-inspection | runtime-observation | expert-review | user-test | interview | survey | field-observation | telemetry | controlled-comparison`.
         An observe* capture is normally `runtime-observation`.
       - `observation`: the fact, what was measured or seen. Required once a method is declared.
       - `interpretation`: the reading, what it means for the criterion. Never write it without an `observation`.
       - `scope`: generalization bounds. Required for every method except `static-inspection`.
       - `population` + `ethics`: mandatory for human-subject methods `user-test`, `interview`, `survey`, and `field-observation`.
         If either is missing, the entry is unusable.
         Record it as blocked evidence; it can support no judgment.
       Entries without the keys stay readable (append-only optional keys), but this orchestrator writes them at every bind.
       Repair a wrong value by appending a newer entry (latest wins), never by rewriting.
  4. Manual provider: when no ecosystem provider exists, a human may operate the surface and save screenshots to `artifact_path`.
     Write the same-format manifest entry (`capture.provider: "manual"`), including schemaVersion=1 and viewport.
     Set `observed_state` to what the human actually saw, not the planned label.
- v1 capture types and their bytes:
  - `screenshot`: png, plus the `.probe.json` sidecar below when the adapter can probe.
  - `a11y tree`: JSON envelope `{"format","tree"}`. The `tree` is Playwright `aria_snapshot` indentation text.
  - `interaction trace`: Playwright trace ZIP. The Provider rejects an `artifact_path` that does not end in `.zip`.

Capture surface (url choice, honesty, not a machine gate):

1. Prefer the live host, running Fill surface (dev server route / real app URL) that implements the decision report.
2. Semantic mirror (static HTML / fixture that only *looks like* Fill) is allowed only when the live host is unavailable or unsafe. Then all of:
   - Every manifest entry's capture snapshot includes `note` (or equivalent) with `surface: mirror` and a one-line reason.
   - ui-evaluator must emit a finding that observe used a mirror, with severity at least low.
     Set `source` to `observe* seam` (or preview*/observe* seam).
     The fix is "re-capture on live host when available".
   - Do not claim G6/process Pass as proof that the Fill tree was runtime-verified.
3. Mirror `data-state` (recommended): when using a semantic mirror, set the page state the provider can read so `observed_state` is not forced to
   `unknown`.
   The evidence adapter reads `body[data-state]` or `[data-state]` (see `mcp/evidence/server.py` `_read_observed_state`).
   Example:

   ```html
   <body data-state="empty">
     <!-- empty-state UI for L6 empty criterion -->
   </body>
   ```

   Prefer one root marker that matches the capture plan's `state` intent.
   Still never invent `observed_state` in the manifest, copy the provider return verbatim (unknown stays unknown).

Evidence is captured, not judged, copy provider returns verbatim here; `pass`/`fail` authority is the evaluator's (step 9 /
`ui-evaluator`).
Full authority model (three ledgers: spec names what to prove, manifest what happened, evaluator what it means): SSOT `ui-evaluator` step 2.

**Done when:** either observe was skipped (no provider, ledger `observed` free-text), or each runtime-proven criterion has a manifest entry
whose artifact exists.
G6 applies when `validate_run.py` is given `--evidence-dir`.
Run its single gate right after manifest binding: `python scripts/g6_evidence.py .scratch/<run>/point-back.md`.
And if any capture used a mirror surface, the point-back includes the required mirror finding.

### 10. Accept with `ui-evaluator`

When the audit-preferences plan reports `ui_evaluator.runs: false`, do not invoke ui-evaluator.
Emit the module-generated skeleton `point-back.md` (`audited: false`, see *Audit preferences*) so the machine chain never breaks.
Record the skip in the skip list and show the run artifact index below as usual.
`run_status` projects *not audited* for such a run.
Never present the skeleton as an audit result.

Otherwise invoke ui-evaluator.
Issues must point back to a declaration.
The report is the six-block `point-back.md` (ledger / findings / positive findings / coverage statement / limitations statement / verdict).
Recirculated blockers route through the two-hop map (declaration artifact then R1-R5) and record the `invalidated:` evidence set.

**Done when:** one of the following audit paths is complete.
If the audit ran, include the criterion-shaped evidence ledger (`criterion / required / observed / result`) and findings as `issue / source / fix / severity / track`.
The authoritative verdict completion criterion in `ui-evaluator` must also hold.
If the audit was skipped by preference, replace the report with the skeleton point-back (`audited: false`).
In either case, show the user a short run artifact index of paths under `.scratch/<run>/`, so declaration products are discoverable.
Include at minimum: `spec.md`, `plan.md`, `decision-report.md`, the Fill surface path, and `point-back.md`.
Also include `design-baseline/` if triggered, `shaping/` if a session ran, and `reference/`, `preview/`, and `evidence/` if present.
One block is enough.
Do not only leave paths buried in tool logs.

Cross-run review of multiple `.scratch/<run>/` runs lives in command run-review (cross-run, not a step of this run).

Machine seam (optional local check): `python scripts/validate_run.py <spec.md> <point-back.md> [--preview-dir <preview/>] [--decision-report <report>] [--evidence-dir <evidence/>] [--run-root <run>]`.

### 11. Static run handoff (optional, on request)

Build the delivery credential only when the user asks to hand this run off to implementation.
It is not a pipeline obligation and never gates acceptance, the authoritative verdict is `point-back.md`.

```bash
python -c "from design_playbook.mcp.evidence.handoff import build_static_handoff; \
  from pathlib import Path; \
  r = build_static_handoff(Path('.scratch/<run>'), Path('<fill-surface>'), round_n=<n>, summary='<one line>'); \
  print(r.index_html)"
```

The builder reads durable run artifacts only.
Its lifetime is independent of any review round.
It needs no review server, no browser session, and no port (ADR-0034).
Everything lands under `.scratch/<run>/evidence/static-handoff/`: `index.html` (the delivery page, package-owned and CDN-free), `disclosure-review.json`, `deliverable.html` (the reviewed
Fill-surface copy the page links), `static-handoff.zip`, `snapshots/`.

Three honesty rules the builder enforces, do not paper over any of them:

- `confirmed` comes from `confirm-round-*.json`, never from a choice label or your own reasoning.
  Without a record, set `confirmationSource: unsubstantiated` and the verdict stays `Pending`.
  Report that as-is.
- Capture targets the Fill surface itself, not the review shell. A zero measured dimension marks the viewport `blocked` and blocks the verdict.
- An untriggered conditional gate is `not-applicable`, not passed. Delivery reads "every gate `pass` or `not-applicable`", never an "8/8" count.

**Done when:** the user asked for a handoff; `index.html` exists under the run tree.
And you reported `verdict` / `authority` / `confirmationSource` verbatim, including a `Pending` one.

## Recirculate

When a finding has no owner or you need the observable-to-declaration routing, use the authoritative recirculate map in `ui-evaluator` (do not
duplicate it here).
Fix only the owning layer, then resume from the step that consumes it.

## Contracts on this pipeline

| Contract | Skill |
| --- | --- |
| Discover, validate, or generate the project visual baseline | `design-baseline` |
| Reference intake (observed and inferred + Keep, Change, and Do not copy) | `reference-intake` |
| Write the functional declaration | `ux-spec` |
| Choose shell + component meaning | `ui-picker` |
| Craft / feedback quality | `craft-guard` |
| Native-feel desktop declaration (render seam + conventions) | `native-craft` |
| Acceptance + point-back critique | `ui-evaluator` |

`plan`, `preview*`, and `observe*` are orchestrator steps (plus optional external MCPs for preview and observe), not rows in this table.
`design-baseline?` is a conditional existing-product orchestrator gate (ADR-0012); `reference-intake?` is a conditional skill step (ADR-0011), not a machine
gate.

Greenfield first-run route and pause table: [`references/first-run.md`](references/first-run.md).

Slash (installed plugin, namespaced): `/design-playbook:design-io` · `/design-playbook:ux-spec` · `/design-playbook:ui-review` · `/design-playbook:run-status` · `/design-playbook:doctor`.
With `claude --plugin-dir` the same command files apply under the plugin namespace.
