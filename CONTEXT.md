# CONTEXT — design-playbook

Domain glossary and product facts for agents. Updated by `/grill-with-docs` / `/domain-modeling`.

## Product

**design-playbook** — Claude Code / Codex **plugin** that runs **Design I/O**: declarations + contracts so UI generation is constrained, reviewable, and recirculatable.

No reading-demo app in-repo (removed). Product surface is the installable package only.

## Glossary

> Evidence exists only to satisfy a declared criterion.
> Providers never produce evidence directly; they produce artifacts that become evidence only when bound by a manifest to a criterion.

| Term | Meaning | Avoid |
| --- | --- | --- |
| **Design I/O** | Pipeline: `design-baseline? → reference-intake? → ux-spec? → plan? → (native-craft?) → ui-picker → (preview*) → fill → craft-guard → (observe*) → ui-evaluator` | “just prompt better” |
| **design-baseline** | Conditional existing-product initialization (ADR-0012): deep module `prepare`/`confirm`/`verify` with `state.json` gate; discover/validate project `DESIGN.md`; missing/stale → provenance-backed draft + explicit confirmation before durable write/Fill | generic style pack; silent overwrite; forgeable confirm files; third-party reference authority |
| **reference-intake** | Conditional declaration input (ADR-0011): screenshot/URL/design/product analogy → run-local `reference/contract.md` + `manifest.json` with observed/inferred + Keep/Change/Do not copy; not a gate | style library; visual Pass/Fail; Fill from reference assets |
| **Declaration** | What good is: spec, domain, craft, design, components, template | “guidelines”, “vibes” |
| **Contract** | How work enters the pipeline: skill timing, evaluator acceptance | “prompt pack” alone |
| **Contract state** | Every persistent contract field is explicitly `decided`, `assumed`, or `open`. Only explicit user confirmation creates `decided`; `assumed` must be acknowledged per run and `open` blocks dependent work. Bind-first resurfaces the latter two and source/schema drift requires review | omitted status as an implicit default; agent self-promotion; calendar-only expiry |
| **Persistent contract v1** | One project-level contract bound as a whole into a run. Run exceptions are explicit decisions that stay local or are promoted after user confirmation. Layered inheritance is deferred until repeated scoped overrides provide evidence for real precedence boundaries | project/page/component inheritance; deep merge; speculative override hooks |
| **Decision log** | Append-only `decisions.jsonl` beside the persistent contract: stable decision ID, field path, choice, rationale, supersession, and confirmation time. Written only after explicit user confirmation; the run ledger binds its SHA | decisions embedded in agent-rewritable `spec.md`; accepting a whole spec as blanket approval; a tamper-proof claim |
| **Closed-loop run** | One Design I/O run that declares the outcome, proves each success criterion, points failures back to their owning declaration, recirculates blocking findings within a bounded retry policy, and stops with an explicit verdict | “generated a page” / “looks done” |
| **Run contract** | The five controls fixed before execution: Goal, Success, Evidence, Stop, Confirm | an open-ended task list |
| **L6 criterion** | One independent user-visible risk or outcome, expressed as Given/When/Then. Three to seven top-level criteria is a soft authoring budget; proof modalities such as accessibility, runtime capture, or multiple stacks attach to the same criterion unless they represent independently blocking outcomes | one criterion per tool, screenshot, stack, or evidence type; a hard count cap that hides real risk |
| **Evidence ledger** | Criterion-shaped acceptance record: required proof, observed proof, and pass/fail/blocked/N/A result for every success criterion | an unstructured review summary |
| **Evidence** | Criterion-addressable artifact: a runtime capture bound by a manifest to an L6.<n>; no criterion → telemetry, not evidence | "observation", "screenshot", an unbound artifact |
| **Recirculate** | Send a failure back to the owning declaration, then resume | blind whole-page restyle |
| **Point-back** | Evaluator finding names `source` declaration + `fix` | “looks off”, “polish more” |
| **Decision report** | ui-picker output before code: scene, template, components, risks | coding from intuition |
| **plan (step)** | Orchestrator-only handoff (`.scratch/<run>/plan.md`): run scope pointers, description→spec map, ui-picker input pack; not a run-contract control and not a machine gate | host Plan Mode; pre-written decision report |
| **preview*** | Optional disposable HTML prototype loop via external MCP tool `preview_prototype`; skip when adapter absent | fill from prototype files; ui-picker step 5 |
| **observe*** | Optional post-Fill runtime-evidence loop via external MCP tool `execute_capture_plan`; provider produces artifacts, orchestrator binds them to L6 criteria via manifest; skip when provider absent | building a runtime/dev server; provider writing the manifest |
| **Capture Plan** | Derived, disposable: L6 Given/When → state+actions, Then → required; never a SSOT, never edited for intent; L6 wins on conflict | a standalone test script; a persisted plan file |
| **Capture contract v1** | Atomic versioned seam for `observe*`: `schemaVersion: 1`, explicit viewport (width/height/DPR/color scheme), and deterministic freeze. The orchestrator snapshots the full request in the manifest; missing/unknown versions fail closed and legacy run-local evidence is recaptured | hard-coded provider viewport; partial rollout; dual-read legacy compatibility |
| **Manifest** | Execution-record SSOT (`.scratch/<run>/evidence/manifest.jsonl`, append-only): self-contained entries binding criterion ↔ artifact; the only seam between Contract and Runtime objects | provider output; an editable log |
| **Provider** | Runtime executor of a capture plan; produces artifacts, never evidence; probed via `tools/list` for `execute_capture_plan`; Playwright MCP / manual / future | collector; judge; a criterion-aware tool |
| **G5** | Conditional `validate_run.py` gate: if preview occurred, require `confirm-round-*.json` with `confirmed=true` and matching `report_ref` | always-on preview gate; scanning Fill source for confirm refs |
| **G6** | Conditional `validate_run.py` gate: if a ledger `observed` references an `evidence/` artifact, require the artifact to exist and a manifest entry to bind it to the matching L6.<n> | always-on evidence gate; scanning Fill source; judging pass/fail from the manifest |
| **G7** | Contract-drift consistency gate: compare bind-first schema/contract/decision-log hashes with normalized v1 fields and the final append-only decision log. Emits stable machine-readable failures for unrecorded drift; never claims to prove user identity or consent | treating an agent-written decision record as self-approval; semantic product judgment |
| **Blocking** | Acceptance failure that must recirculate (L5/L6, unsafe ops, …) | optional polish |
| **Dogfood** | Run Design I/O on a real UI ask to test *process*, keep answer not demo code | shipping the throwaway page |
| **run aggregate** | Cross-run rollup from `scripts/aggregate_runs.py`: per-run status table + repeat-blocker frequencies over `.scratch/**/dogfood/*/` runs; JSON is the contract surface, markdown the view. Stays separate from `doctor.py` — doctor diagnoses install-state health of the distributable surface, aggregate reads this repo's run history; installed users have no `.scratch` (roundtable 2026-08-02) | a run ledger; prose “lessons”; a doctor check |
| **repeat blocker** | A blocker whose normalized `observed` text recurs across runs; systemic-defect signal; counting only, never judging (v0.9) | “we should learn…” narratives |
| **stable main** | Public distribution branch whose version and installable inventory exactly match the latest formal release; unreleased capability stays off `main` until its release gate passes | rolling development branch; prerelease surface under a released version |
| **release transaction** | Gated promotion of one identical release commit to `main`, semver tag, and public registries; before promotion, `main` remains the previous formal release | merge-first release prep; independent version bumps |
| **SSOT** | Single source of truth for a declaration snippet | dual-edit attachments + references |
| **Native-feel** | Desktop app indistinguishable from native; render-surface seam + native conventions; declared by `native-craft` | “theme Electron”, “web page in a window” |

## Decisions (grill)

- **vNext persistent contract governance:** user confirmation is the sole authority for `decided`; bind-first must resurface `assumed` / `open`, and durable decisions live in an independently hashed append-only log (ADR-0017).
- **vNext capture contract:** schema v1, viewport, freeze, manifest snapshot, validation, and tests ship as one atomic change; old run-local evidence is recaptured (ADR-0018).
- **vNext inheritance boundary:** persistent contract v1 binds at project scope only; layered inheritance waits for repeated cross-scope override evidence (ADR-0019).
- **vNext G7 boundary:** G7 checks artifact linkage and unrecorded field drift only after its three prerequisites land; user authorization remains an explicit process decision (ADR-0020).
- **First user (v0):** public install — strangers install via marketplace/documented path; distribution + license posture are in-scope for ship.
- **Success (v0 run):** L5/L6 `spec` → decision report before code → point-back accept → recirculate blocking; plus install docs strangers can follow.
- **Scope shape (v0):** cut style CSV DB, multi-platform CLI, Figma-as-dependency, demo redesign-as-delivery; **add** license boundary, copy-paste install, clean self-authored examples, stack-with-ecosystem README, craft-guard dogfood.
- **License surface (v0):** public plugin may redistribute **only** our authored skills/commands/workflow/install docs + **self-written** examples. Upstream manuscript, figures, ACD marks, demo chrome, and unre-written `public/attachments` are **not** the plugin ship claim (demo may stay local learning copy with rights notice).
- **SSOT (v0):** declaration snippets live only under `packages/design-playbook/skills/*/references/*`. **Reference ≠ port:** inspired by Design I/O ideas, not an overlay/migration of any upstream playbook corpus.
- **Repo shape (v0):** product package `packages/design-playbook/`; demo site removed; root holds docs/scratch/workflow only (ADR-0005).

## Non-goals (v0)

- Competing with ui-ux-pro-max style databases
- Multi-agent-platform install CLI
- Figma MCP as a required delivery path
- Treating demo-site visuals as the release artifact
- Dedicated-hardware input surfaces; input/navigation ideas enter only as 2D declaration/evidence extensions (ADR-0010)

## Layout

| Path | Role |
| --- | --- |
| `packages/design-playbook/` | Public plugin product (skills, commands, bundled MCP) |
| `packages/design-playbook/mcp/` | Bundled Preview + Evidence MCP runtimes (marketplace install path) |
| `packages/design-playbook-preview/` | Compatibility launcher + docs for Preview MCP (`preview_prototype`) |
| `packages/design-playbook-evidence/` | Compatibility launcher + docs for Evidence MCP (`execute_capture_plan`) |
| `packages/design-playbook/skills/` | Skills SSOT |
| `docs/agents/` | Tracker + product workflow |
| `.scratch/<run>/` | Single-run artifacts (design-baseline / reference / spec / plan / decision / preview / filled-ui / craft-guard / evidence / point-back) |
| `.scratch/<effort>/` | wayfinder decision maps (`map.md` + `issues/`) |
| `docs/adr/` | Decisions |

## Active effort

- **v0.11.1 released (2026-08-07):** npm Trusted Publishing is live through GitHub Actions OIDC with SLSA provenance; Canvas anchor focus no longer races a later user focus change. Release commit/tag `d6e4d47`; workflow run `31196686506`; GitHub Release; npm `latest=0.11.1`. Evidence: `.scratch/design-playbook-v0/evidence/install-smoke-v0.11.1-2026-08-07-retry1/result.md`.
- **Install smoke automation hardened (2026-08-07):** `scripts/install_smoke.py` runs isolated marketplace install, exact inventory check, real MCP handshakes, npm consumer validation, and encoding-safe console output; `tests/test_install_smoke.py` has 12 deterministic tests; wired into `.github/workflows/ci.yml` and `docs/agents/release-checklist.md`.
- **Distribution paused:** `@claude-community` catalog submission pack ready but paused by user decision. Resumption requires a human with an eligible Anthropic Console account at https://platform.claude.com/plugins/submit.
- **No active feature cycle:** per ADR-0015, `main` stays equal to latest formal release (`0.11.1`). Next product version waits for external user signal or resolved distribution blocker.
