# Narrow repair map

After Recirculate, change the **smallest owning declaration**, re-evaluate only affected L6 criteria, and recapture only invalidated evidence.

| Failure class | Owning declaration | Affected evidence |
| --- | --- | --- |
| Wrong goal / non-goal / always-ask-never | `spec` L1 | All criteria that assumed the old L1 |
| Missing edge path | `spec` L5 | Criteria that name that edge |
| Broken acceptance criterion | `spec` L6.<n> | Only that L6.<n> row + its artifacts |
| Component role mixup | `components` / decision report | Criteria that depend on that role |
| Craft hierarchy / motion | `craft` | Craft-backed criteria only |
| Capture contract / viewport mismatch | observe* seam | Recapture those artifacts (overwrite or revision name) |
| Stale screenshot after Fill change | Fill + observe* | Invalidate bound criteria whose observed UI changed |

## Second hop: declaration then R1-R5

Routing is two hops (first hop above; second hop picks the repair target). Repair order follows declaration-layer dependency R1 then R2 then R3 then R4; R5 (evidence plan) may append after any layer. Take the **minimum owning set**. Multi-layer findings may carry multiple `source:` values.

| Route | Repair target | Trigger (finding features) | Landing action |
| --- | --- | --- | --- |
| R1 | requirement (reopen shaping subtree) | No owning declaration exists (ownerless finding). Criterion unjudgeable (Given, When, and Then gap). An `assumed` field falsified. Non-goal boundary disputed | Reopen only the falsified subtree via a new shaping session (`superseded_by`). Revise decisions via `supersedes`. Never invent product requirements in review |
| R2 | interaction model (`spec` L2-L5 structured fields) | Five-state missing. Path break. Decision point / return-preservation unmodeled. Page duty missing | Patch the structured spec rows. Re-evaluate affected L6 |
| R3 | design decision (decision report) | Direction-level assumption failed. Trade-off unrecorded. Visual direction conflicts with baseline | Revise / append the decision report. Re-confirm preview when it applies (G5) |
| R4 | implementation (Fill) | Implementation deviates from the confirmed model: action missing, wrong state, token scatter, component misuse | Fix the implementation. Resume from the step consuming the declaration |
| R5 | evidence plan (observe* seam) | Method cannot answer the criterion (capture seed mismatch). Provider absent. Sample and environment mismatch. Evidence insufficient while implementation is right | Fix the capture plan / provider / recapture. Implementation and declarations untouched |

Session `storage_state` blocked (next owner is always the operator, never an auto-login):

| Blocked class | Operator action | Resume |
| --- | --- | --- |
| path (escape, absolute, bad shape) | Correct the run-root-relative `.json` path | Recapture the same Then |
| file (missing, unreadable, non-object JSON) | Provide a readable Playwright storage_state object | Recapture |
| expired / wrong page (`observed_state` is login or `#app` missing) | Refresh the authorized local session | Recapture with target selector |
| unsupported mechanism | Choose a supported local session file. Do not invent login | Recapture or mark blocked |

## Evidence freshness

- Fill changes that can affect a bound criterion **invalidate** prior evidence for that criterion.
- Replacement artifacts use `overwrite=true` or a new revision filename. The latest manifest entry wins.
- If the ledger still cites a superseded artifact name, emit a **warning** (not a hard Pass) with owner, expected, actual, and repair. Then recapture or update the ledger.
- Unaffected criteria keep their evidence.

## Invalidated evidence set (`invalidated:` block)

Record the minimal invalidated set in `point-back.md` when recirculating. The set is computable: directly affected criteria plus criteria derived from a falsified contract field (via its `notes` source chain). Everything else keeps its evidence. History is preserved, superseded artifacts keep overwrite or revision naming and the latest manifest entry wins.

```text
invalidated:
  - criterion: L6.2
    artifacts: [evidence/L6.2-cap-error.png, evidence/L6.2-a11y-tree.json]
    reason: Fill fix changed the cap-limit toast; rendered evidence stale
  - criterion: L6.3
    artifacts: []
    reason: capture provider session loss; R5 capture-plan revision, no artifacts existed
```

Re-evaluation runs the invalidated set plus adjacent primary-path nodes only (minimum repair). The two-cycle stop policy for a repeated blocker stays in force.

## Paired repair evidence

Complete acceptance derives one proof obligation from every blocking finding a
single closure claims to close. The finding names the criteria; the closure
carries the pair; the ledger carries the retest:

```text
issue: empty state primary action is hidden
disposition: blocking
criteria: L6.3
evidence: evidence/L6.3-empty-r1.png

- closes: <id or exact issue value> -> recirculate -> fix -> re-eval -> 0 blocking
  repair-evidence: criterion=L6.3 before=evidence/L6.3-empty-r1.png after=evidence/L6.3-empty-r2.png
```

- `criteria:` holds one or more exact `L6.<n>` tokens. A closed blocker with no
  criteria, an unknown criterion, or a duplicate fails closed. An annotation
  may omit `criterion=` only when the finding declares exactly one criterion;
  it then inherits that one value.
- The closure must resolve to that finding alone. A shared issue text or an
  `id:` that collides with another finding's issue cannot be consumed.
- **Visible-state (screenshot) repairs** need exactly one named pair per
  closure x criterion. `before` must be the finding's own `evidence:`
  artifact; `after` must be the artifact the criterion's current ledger row
  observes. Both halves bind through `evidence/manifest.jsonl` to that
  criterion and share one complete viewport; a required pair must declare
  matching SHA-256 digests.
- **`a11y_tree` / `interaction_trace`** repairs retest in their declared type
  and do not require screenshots. An explicitly written pair is still
  validated, but its absence creates no visual obligation.
- **`automated_check` / `declaration_coverage`** keep the evaluator's existing
  judgment boundary. A free-text observation needs no capture request; a
  referenced `evidence/` file still passes the same binding and integrity
  checks.
- Byte-identical *visual* halves are `G4.repair_evidence_unchanged`: the pair
  is insufficient to demonstrate the declared visible change - not a claim
  that the function still fails. Changed bytes never establish criterion
  success either; the criterion's ledger result must pass.
- `--legacy` and explicit `--require-*` selections keep the structural
  reading: an annotation that exists is validated through the same G6 owner,
  but no pair or proof-type obligation is invented and the result must not be
  reported as complete acceptance.

`scripts/validate_run.py` owns the judgment (rules `G4.repair_evidence_*` and
`G4.repair_association_*`; artifact facts and integrity keep their `G6.*`
codes). Neither this map nor the closure line re-decides it.

