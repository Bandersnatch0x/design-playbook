---
name: ui-evaluator
description: Run evidence-backed UI acceptance. Use after generating a page, or when the user wants a design review or recirculatable critique against declared goals and success criteria.
context: fork
agent: design-playbook:ui-evaluator
background: false
---

# ui-evaluator

**Evaluator** contract: turn **declarations** into checks. Do not invent new taste standards. Every issue **points back** to a declaration.

## Isolation

Run in a fresh child context, never in the producer's conversation. This skill declares
`context: fork` with the read-only `design-playbook:ui-evaluator` agent; on verified host build
2.1.318 the child starts from this skill text plus the delegation arguments and receives no
producer chat, plan notes, self-assessment, or preferred verdict.

Inputs are the delegation's **allowed set**: the run root's observation artifacts; the dependency
paths the delegation names explicitly, as absolute paths prepared by the caller; this skill's
`references/`; and the public rule registry index with the `rules/` part files it links. Producer
conversation, plan notes, and prior-turn justification are **not** inputs — a claim that cannot be
re-derived from those artifacts does not exist for this review. Missing or unreadable evidence stays
`blocked`; never rebuild it from source or from narration. Inherited declarations count when an
artifact names them by path or value, never as a transcript.

Read nothing outside that set. File entries are exact paths: a named file is read directly, and
only a listed directory may be enumerated with `Glob` or `Grep` — never Glob a parent directory to
find a named file. A relative declaration that does not resolve uniquely inside the set is
`blocked`; never search the worktree, the package, or a neighbouring run to find it.

Review outputs are not inputs. A `point-back.md`, a `raw-child-final.txt`, or an archived review
conclusion — under any name or copy inside the run — is the artifact this review replaces or a
prior verdict. On a first review they are excluded. Only when the delegation declares an explicit
re-review may you consume the named history entries (ledger rows, finding ids, closure records) —
never the prior verdict, coverage, or limitations prose.

**Formatting-only correction mode** is the one exception: the delegation may supply exactly the
complete current report plus the named machine format errors as immutable source. You then change
only the named structural fix; every finding, evidence result, and the verdict stays unchanged. It
is not a re-acceptance, and a truncated or incomplete report never enters it.

Preparation reads only the allowed set: no personal session history, memory files, or
proof/verification scripts.

Source alone is not rendered proof; with no bound artifact the row is `blocked`, not a pass.

This is conversation isolation, not an OS or filesystem sandbox. `Read`, `Glob`, and `Grep` can
technically reach any path the host permits, so the evidence is the input discipline plus the tool
trace the caller audits. In the Limitations statement, name the roots you actually read and every
path outside the allowed set; a trace outside the set is not artifact-only evidence. A check that
inspects the conversation for earlier turns is defense-in-depth only — it depends on the model
obeying it and is not a host-enforced detector.

If the host starts no fresh child context, isolation is unavailable. Report `isolation: unavailable`
and name the fresh-context or manual-review path; never run the review inline and label it isolated.
The producer may know the public criteria and rubric; isolation removes producer history and
self-assessment, not the acceptance standards. Measure against the current registry and the bound
evidence.

## Steps

### 1. Bind declarations

Identify which of these apply to this surface (the run artifacts and the declarations they name by path or value, or design-playbook defaults):
`spec` · `domain` · `craft` · `design` · `components` · `template`.

When a verified `.scratch/<run>/design-baseline/state.json` binds a baseline (`status: ready`, path from `baseline.path`), include it as the project-specific visual declaration. It can support design-drift findings but is never L6 runtime proof by itself. An explicit `status: waived` disables baseline-drift checks for that run. It does not waive `spec`, accessibility, or craft checks.

When `.scratch/<run>/reference/contract.md` exists (ADR-0011), you **may** use it as supporting context for **Do not copy** findings. These include copied brand chrome, distinctive illustration, or other breaches. Set `source` to `reference` or the owning declaration. It is **never** L6 proof and never a Pass or Fail gate by itself.

**Done when:** the check set is named. If `spec` L6 exists, every criterion and its required proof are on the list.

### 2. Run checks

Walk every applicable row (exhaustive for bound declarations):

| Check | Source |
| --- | --- |
| Empty / loading / error / permission | `spec` |
| Risk color, secrets, dangerous ops | `domain` |
| AI slop, hierarchy, purposeless motion | `craft` |
| New surface drifts from confirmed project visual roles and patterns | bound `<binding.path>` |
| Raw hex / px / ms (unlogged) | `design` |
| Badge and Tag, Dialog and Drawer, … | `components` |
| Shell matches scene | `template` |
| Each L6 acceptance item | `spec` |
| Required proof exists for each L6 item | `spec` |

Dimension selection, recirculate examples, the preview-seam health check (required when the run produced `preview/` artifacts), and the **observe\* mirror-surface** finding (required when any manifest capture notes `surface: mirror`): [`references/rubric.md`](references/rubric.md).

When L6 proof includes an `a11y tree` artifact, interpret it with [`references/a11y-tree.md`](references/a11y-tree.md) (names, roles, states, keyboard path, focus, material omissions). Record accessibility evidence on the owning user-risk criterion. Do not invent separate taste standards.

When `.scratch/<run>/craft-guard.md` exists, consume exactly one seven-column audit row for every registry craft entry whose applicability predicate evaluates to `applicable`. Use the full catalog, or every **enabled** subset row when the contract declares a smaller set. Registry index: [`../design-playbook/references/rules.md`](../design-playbook/references/rules.md); entries live in its `rules/` part files. Summarize the applicable count, and warn when every evaluated entry is `not-applicable`, any `not-applicable` row lacks an observable reason, or the `blocked` rate is abnormal. Audit rows are advisory. Verify their rendered and source evidence and exception checks. Use the authoritative recirculate map below to choose declaration source and assign severity. A detector never decides source, severity, or verdict. Carry every `blocked` row into evaluation as a craft proof gap. Implemented UI cannot claim complete craft Pass while required rendered or source proof is blocked. Planning-only work records an explicit `not-applicable` reason without claiming rendered inspection. Keep craft detector rows out of the G6 manifest and L6 evidence ledger: they are craft-stage audit records, not runtime artifacts or criterion results.

Record an evidence ledger before writing findings. Every L6 criterion has exactly one row:

```text
criterion: L6.<n>
required:  <declared proof>
observed:  <artifact path, interaction, check result, or missing>
result:    pass|fail|blocked|N/A
```

`observed` is either an **artifact path** (relative to the run root, e.g. `evidence/L6.3-error.png`) when a runtime capture was bound by a manifest, or **free-text** describing a manual observation. Both are legitimate. The machine seam (G6) only validates artifact-path references. When using an artifact path, keep the path as the **leading token** of the line (e.g. `observed: evidence/L6.3-error.png`). Trailing commentary is tolerated by G6; it reads the leading token, breaking on whitespace, `(` / `（`, or `,` / `，` / `:` / `：`. Other punctuation (em dash, slashes, etc.) will be treated as part of the path, so put elaboration on a separate `note:` line for clarity when unsure.

Evidence is captured, not judged. A manifest entry records that an artifact was collected at a state; it does not say the criterion passed. `pass`/`fail` is this evaluator's verdict against `required` vs `observed`. A screenshot can prove a criterion false. Three ledgers, each one authority: `spec` L6 names **what to prove**. The manifest records **what happened**. This ledger decides **what it means**. Providers produce artifacts. The manifest binds them to criteria. The evaluator decides. A manifest entry is binding and request metadata, not an execution result: when the artifact is missing or the tool cannot read it — for example an unopenable binary trace — the criterion stays `blocked`, and the manifest's action or state fields never substitute for the artifact. A single static screenshot proves one state, not continuous update; a continuous-progress claim needs the interaction or sequence record. For a `page-probe/v1` sidecar, read `layout.measurement_status`, `defects.measurement_status`, `console.measurement_status`, and — when the capture carried a `design` — `renderTokens.measurement_status` **before** interpreting `leaks` / `tapFails` / `consoleErrors` / `renderTokens.findings`; `blocked` or `unmeasured` is ledger `blocked`, never a clean pass. An empty `renderTokens.findings` array is not a pass on its own: it is empty both when the bound axes conform and when they were `undecidable`, so a non-empty `renderTokens.undecidable` blocks those axes. The `design` echo is the **caller's declaration**, not a confirmed user decision — do not read it as the user having approved a palette, type scale, or radius system. Those arrays are candidate observations, not automatic blocking. A fail or blocked L6×viewport pair is not rescued by another viewport's pass. `captured`/`ok` is not proof the declared target page was reached.

For implemented UI, visible-state proof is a rendered inspection at the declared target viewport. Behavior proof is an interaction trace or automated check. Code-health proof is the relevant available test, type and lint, or affected build result. Planning-only proof is declaration coverage and must not claim a render or test occurred. Non-L6 declaration checks may be supporting observations or findings. They do not enter the machine ledger.

The host model may have no vision (text-only input). Reading a screenshot would break such a session, never make viewing an artifact a review action. Render artifacts stay bound as path references (manifest + ledger `observed`). Machine assertions judge the **text face**: HTML and CSS source, `a11y tree` text, and interaction-trace action records. An interaction trace is a Playwright trace **ZIP**. Unzip before reading; the artifact is not JSON. A no-vision run reviews this way end to end without degrading the protocol. Note it once in the Limitations statement ("this run was reviewed on text-face evidence").

**Done when:** every bound row was considered. Every L6 criterion has exactly one non-empty `criterion / required / observed / result` row keyed as `L6.<n>`. Results use only `pass|fail|blocked|N/A`. Any unavailable required proof is `blocked`, not skipped.

### 3. Emit point-back findings

```text
issue:    <observable>
source:   <declaration>
fix:      <next edit>
severity: S3|S2|S1|S0
track:    product|interaction|cross-cutting
```

Severity is the **consequence axis**: S3 blocking-severity, S2 major, S1 minor, or S0 positive or info. Grade by user-visible impact and reference the affected L6 or primary-path node. The legacy values `high (blocking)|high|med|low` are **no longer legal** (alias period ended, v0.20.0 breaking change). They are structural errors at G2. Write the axis values directly: `high (blocking)` maps to S3 + `disposition: blocking`, `high` to S2, and `med` or `low` to S1.

`track` is required: every finding declares which review track produced it, `product` (per-L6 acceptance), `interaction` (primary-path walkthrough dimensions), or `cross-cutting` (applicability-matrix families). The machine seam is unchanged (G2 validates the value only when the line is present). An omitted track is a review defect to fix here, not a structural error.

Additional field lines (machine-tolerated; validated when present) complete the review axis:

```text
confidence:  high|medium|low   (evidence layers x reproducibility x judging subject)
disposition: blocking|advisory|info   (severity x fact/judgment class x confidence)
evidence:    <artifact path or source ref, may repeat>
assumes:     <assumed contract field paths the finding depends on, if any>
rule:        <registry ID@version refs, when a registry rule is involved>
dd:          <decision-report entry ref, when a design decision is challenged, never on positive (S0) findings>
id:          <run-unique token>
status:      open|resolved|new|regression  (optional; omit = no re-review annotation, not a second closure authority)
```

On a **new P2/P3 observe\*** blocking finding, assign a non-empty run-unique `id` on first write and **reuse it** when the issue text is rewritten. Older reports without `id` stay legal; G2 does not backfill them. `status` never overrides a current `- closes:` line.

When a previously closed blocker **regresses**, keep the same `id`. Move the old `- closes:` line into `history:`, where it must not match `CLOSURE_LINE`. Put the stale artifact on `invalidated:` and recapture new evidence. Before Pass, write **exactly one** current `- closes:` against that new artifact.

Probe arrays may contain secrets (cookie, token, and session text in `leaks` or `consoleErrors`). In point-back and any shareable summary write `seen, omitted`, do not copy the secret string. The sidecar file stays the fact store.

Severity and disposition are **two axes**. A judgment-class S3 (subjective, semantic, or representativeness) is never directly blocking. List it in the Limitations "pending user adjudication" sub-block. Offer three options: change declaration, accept risk, or promote to the rule-registry queue. Only fact-class S3 (reproducible, evidence-bound) takes `disposition: blocking` and enters G4 closure.

Order: **blocking** first (broken L5/L6, unsafe dangerous ops, removed focus rings), then polish.

**Done when:** every finding has all five fields (track included). No “generally improve the design” lines. Additional fields use only their declared value sets.

### 4. Verdict

- Emit exactly one `## Verdict` section containing exactly one anchored verdict: `Pass` or `Recirculate`.
- **Pass.** zero blocking. Every L6 criterion has exactly one evidence row. For Pass, every required evidence row passes (every evidence result is `pass`). Token gaps are logged or fixed.
- **Recirculate.** each blocking `source` names the step and declaration to reopen in design-playbook; `fail` or `blocked` evidence remains visible.

For a repaired blocker, record exactly one closure line whose target is the finding `id` when present, otherwise the issue text (same normalisation as G4):

```text
- closes: <id or exact issue value> -> recirculate -> fix -> re-eval -> 0 blocking
  repair-evidence: before=evidence/L6.3-empty-r1.png after=evidence/L6.3-empty-r2.png
```

The `repair-evidence:` line is the pair behind the closure, and it is the finding's required proof: the failing half and the repaired half, each
bound through `evidence/manifest.jsonl` to the same criterion and the same `request.viewport`. Half a pair is `blocked`, so the closure does not
close and the verdict stays `Recirculate` — never `Pass`. Do not write the pair from memory or from the producer's narration; it is the capture
the manifest already binds.

Repeat-state detection is not narration either. Identical bytes on both halves is `G4.repair_evidence_unchanged` (the failing surface is still
standing). A blocker reappearing after a repair keeps its `id` and increments `rounds:`, and the existing two-cycle stop in
[`references/repair.md`](references/repair.md) is the checkpoint — two rounds without new evidence stops the recirculation. The machine face is
`scripts/validate_run.py`; it decides the pair once, so neither the loop nor a second gate re-implements the verdict.

**Done when:** the explicit verdict is structurally unique. Blocking sources are non-empty. Every blocking finding has exactly one matching closure before `Pass`. A blocking finding cannot be waived inside a Pass artifact. Without a user in the loop, blocking findings remain in recirculate and the run requests a decision. Re-evaluate only after an explicit user decision updates the owning declaration or severity. Record it against the user's statement or decision record. The final Pass artifact contains no blocking severity.

### 5. Six-block report structure

The report artifact remains `point-back.md` (no new file). The machine face is unchanged, four-field findings, four-field ledger rows, closure lines, verdict semantics, and existing parsers tolerate the new blocks. The full structure:

```text
## Evidence ledger          (one row per L6; required rows may note assumed deps)
## Findings                 (five fields + additional field lines)
## Positive findings        (S0/info rows + pattern-level positives; AC-level
                             positives are the ledger pass rows themselves)
## Coverage statement       (exhaustive-review completion / sampling + reasons /
                             explicit unreviewed list; G11 checks existence)
## Limitations statement    (judgment-class dimensions, no-user-evidence scope,
                             pass scope, assumed dependencies, machine-face
                             boundary, text-face review note when no visual
                             evidence was read, pending-user-adjudication
                             sub-block)
## Verdict                  (exactly one Pass|Recirculate + closure lines)
```

An empty Findings block is a fact, not an omission: keep the `## Findings` heading and write the single literal marker line `findings: none` inside it. Never transcribe a placeholder ('none blocking', 'not applicable') into finding field values, a placeholder is not a finding, and cross-run derivation groups field values verbatim.

Keep entries concise, but never drop a criterion, a necessary finding, or a matrix cell for length. Do not replace content with a truncation marker, and do not switch models to fit a limit.

Coverage levels:
- **exhaustive**: primary path, required rare paths, and per-page five-state matrix, with no exceptions.
- **sampled**: edge cases by five-state x page matrix, with reasons recorded.
- **explicit unreviewed**: everything else, never defaults to pass. Unreviewed is not pass: it produces no pass contribution.

When the run profile is P3, the Coverage statement carries the sampling matrix the machine gate reads — the marker line, then one line per spec-declared L5 cell:

```text
采样矩阵:
- <page>/<state>: <sampling evidence or capture>
- <page>/<state>: 未审 — <reason>
```

A missing cell line is a coverage gap, not prose to summarize. Keep the marker and one line per declared cell even when most cells are unreviewed.

Positive findings are acceptance evidence, not decoration. Every L6 `pass` on implemented UI requires at least one bound rendered or interaction artifact. Measurement and source corroborate but never carry a pass alone. Planning-only passes rest on declaration coverage and must not claim a render or test occurred. Missing evidence is `blocked` (unverifiable), never `fail`, "not tested" and "tested and failed" are different facts.

**Done when:** all six blocks are present. The Coverage statement names the exhaustive completion status and the explicit unreviewed list (G11). Every pass row cites bound evidence. Limitations name the judgment-class dimensions, assumed dependencies, and the roots actually read. Return the report as your final message; do not write files or run commands. The caller writes the returned text verbatim to `point-back.md` and runs `python scripts/g2_g4_pointback.py .scratch/<run>/point-back.md` right away, without waiting for the end-of-run `validate_run.py` sweep.

If the caller returns the machine validation's structure errors for a complete current report, use
the formatting-only correction mode: correct only those structures — block names, sampling-matrix
lines, repair-evidence pair bindings, a coverage marker's case — and keep every finding, evidence
result, and the verdict unchanged. Structural repair is not a re-judgment.

After Recirculate, use [`references/repair.md`](references/repair.md) for the smallest owning declaration, the R1-R5 second-hop route, and which evidence to invalidate.

The artifact shape behind this verdict is machine-checkable. `scripts/validate_run.py` gates L1-L6 and ordered `Given, then When, then Then` in every top-level L6 item. It requires one non-empty four-field evidence row per `L6.<n>`, allowed evidence results, and all-pass evidence for `Pass`. It also requires four non-empty finding fields, one explicit verdict, and one exact issue-linked closure per blocking finding. When a closure declares `repair-evidence:`, it requires both halves bound to one criterion and viewport (`G4.repair_evidence_*`). These checks are the completion criteria above, not extra prose.

After Recirculate, use [`references/repair.md`](references/repair.md) for the smallest owning declaration and which evidence to invalidate.

## Recirculate map (authoritative)

Single source of truth for routing an observable to its declaration. The orchestrator and other skills point here. Do not duplicate it. Routing has two hops. First map the observable to a declaration artifact. Then map the declaration artifact to an R1-R5 repair target. See [`references/repair.md`](references/repair.md) for the full second-hop table and the `invalidated:` evidence-set block.

| Observable | Declaration | Second hop (default) |
| --- | --- | --- |
| Happy path only. Empty, fail, and auth missing | `spec` | R2 (interaction model: five-state / path rows) |
| Wrong business meaning / risk / secrets | `domain` | R1 (requirement subtree reopen when undeclared) |
| AI slop, flat hierarchy, purposeless motion | `craft` | R4 (implementation) |
| New UI visually conflicts with confirmed existing-product baseline | bound `<binding.path>` | R3 (design decision) |
| Scattered hex, px, and ms | `design` | R4 |
| Badge↔Tag, Dialog↔Drawer mixups | `components` | R4 |
| Wrong page shell (e.g. list as card wall) | `template` | R4 |
| Desktop app feels like a web page / wrong seam | `native-craft` | R4 |
| Copied third-party brand / Do not copy breach | `reference` (supporting) belongs to fix in Fill / re-intake | R4 |
| Undeclared product requirement / unjudgeable criterion / falsified assumption | re-open `ux-spec` shaping | R1 |
| Capture plan cannot answer the criterion / provider absent | observe* seam | R5 (evidence plan) |
| Critique with no owner | re-run `ui-evaluator` |, |

Fix only the owning layer (minimum owning set). Repair in order R1, R2, R3, then R4; R5 may append after any layer. Resume from the pipeline step that consumes it.

## Guard

Prefer positive fixes in `fix`. Reserve bans for non-negotiables (e.g. open dangerous action without confirm) and always pair with the required behavior.

## Excuse table

Every row is an excuse for skipping a step, paired with the consequence that already applies. No row adds a penalty.

| Excuse | Why it does not hold | Existing consequence |
| --- | --- | --- |
| "Captures are unavailable / the environment is not set up" | Unavailable required proof is `blocked`, not skipped | `blocked` evidence row; Pass requires every required row `pass`, so the verdict is Recirculate |
| "The change is small / it is only a point fix" | Scope is not evidence; a criterion with no bound artifact stays unproven | Same `blocked` row; an evidence-plan seam goes to R5 |
| "It passes on my viewport" | A criterion is bound per viewport pair | A fail or `blocked` pair is not rescued by another viewport's pass |
| "The producer says it works" / "we settled it in the session" | Producer narrative is not a bound artifact (see Isolation) | `blocked` row, Recirculate |
| "The craft rows were advisory anyway" | Advisory rows carry blocked proof into evaluation | Blocked craft proof is a proof gap; Pass cannot claim complete craft |
