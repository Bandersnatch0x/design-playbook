# Run Snapshot v1 authority parity and fixture design

Status: Packet 03 implementation input. This document maps the accepted
[Run Snapshot v1 contract](./2026-08-25-run-snapshot-v1.md) to authorities that
exist in the repository on 2026-08-25. It does not implement a producer,
Console, locator registry, or fixture.

Normative boundaries:

- [ADR-0035](../adr/0035-run-view-projection-authority.md): the Run View is a
  rebuildable projection, never an authority.
- [ADR-0037](../adr/0037-local-single-run-console-lifecycle.md): read parity
  precedes every typed action.
- [ADR-0038](../adr/0038-run-snapshot-contract-and-loopback-security.md):
  availability is explicit and Source locators are opaque and run-scoped.

`MUST`, `MUST NOT`, and `SHOULD` are normative. A row marked **gate** has no
proven owner-local public projection today. It emits `unknown` with
`owner-unmapped` (or disables the action) until the named owner supplies the
seam; Console code MUST NOT fill the gap.

## 1. Parity rule

Parity is binary and semantic. For a captured immutable source set, the
snapshot projection and the existing owner path MUST agree on the typed fact,
its availability, and its source binding. A green page, matching prose, or a
second regex is not parity.

Every assertion ID is stable. Array assertions use the shown ID template and a
stable owner-provided domain ID. All assertion `source.refs` are sorted and
unique. `known` requires equal observed and verified source-set hashes.

## 2. Authority and Source registry

Locator classes are logical allowlist classes, not paths. `artifact-excerpt`
and `authority-record-excerpt` may resolve only to a bounded, server-rendered,
read-only semantic excerpt. `non-viewable` always has a null locator.

| Source key / ref template | Unique owner | Reused read seam (no copied parsing) | Source kind / locator class | Availability and failure mapping | Representative existing fixture/test | Binary expected parity |
| --- | --- | --- | --- | --- | --- | --- |
| `session.selected-run` / `source.selected-run` | Console launch session; semantics are only the explicit selection and canonical contained root | New session-selection fact over the launch argument; no run file owns it | `session-selection` / `session-selection-summary` | Valid contained selection is `known`; invalid selection aborts build, not an assertion fallback | `tests/test_run_status.py` temporary run roots | Snapshot `runId` is derived from the selected run identity; browser input cannot change the selected root |
| `package.metadata` / `source.package-metadata` | Installed package metadata | Owner-local adapter reading packaged `.claude-plugin/plugin.json` (the same file checked by `scripts/doctor.py`) | `package` / `package-summary` | Complete supported metadata is `known`; missing/unreadable/malformed maps to the matching source reason | packaged manifest checks plus `scripts/doctor.py` | Name is exactly `design-playbook`; version equals the installed manifest version |
| `run.profile` / `source.run-profile` | `scripts/run_profile.py` | `RunFacts.run_profile` from `parse_run_profile`; validate with `validate_run_profile`; effective tier also applies recorded upgrades via `effective_tier` | `authority-record` / `authority-record-excerpt` | Absent plan/profile: `not-produced` or `source-missing` by lifecycle; parse/validation failure: `source-malformed`; unsupported profile: `source-version-unsupported` | `tests/test_run_profile.py`, `tests/test_run_facts_snapshot.py` | Declared/effective tier and human confirmation fact equal owner output; raw `confirmed_by` identity is never exposed |
| `intent.specification` / `source.specification` | `scripts/g1_spec.py` | **Gate:** add owner-local `SpecificationProjection`; existing `check_spec` and private `_l6_items` are validation evidence, not a public projection | `artifact` / `artifact-excerpt` | Missing/not produced/unreadable/malformed map normally; until the seam exists, summary and every criterion are `owner-unmapped` | `packages/design-playbook/tests/fixtures/pass/spec.md`, `fail/g1-*` | Summary and each `intent.criteria[*]` equal the owner projection; Console contains no L1/L6 regex |
| `intent.contract` / `source.contract-bind` | `scripts/contract_v1.py` plus G7 bind authority | `load_contract`, `load_decisions`, `bind_first`/`BindResult`; G7 diagnostics verify drift | `authority-record` / `authority-record-excerpt` | Contract errors map malformed/unsupported; absent bind is `not-produced`; non-current source hashes make the assertion stale; owner-reported open/assumed/stale fields remain domain results | `test_contract_v1.py`, `test_g7_contract_drift.py` | Sorted fields and `blocking == bool(blockers)` equal `BindResult`; no Console re-evaluation |
| `execution.stage-registry` / `source.run-facts` | `scripts/stages.py` and `scripts/run_status.py` | one `capture_run_facts` result passed to `inspect_run`; `STAGES` supplies labels/order | `authority-record` / `authority-record-excerpt` | Capture read errors affect only dependent stages; unsupported or ambiguous skip semantics are not inferred; absence is a known stage presence only when the owner defines it | `tests/test_stages_registry.py`, `tests/test_run_status.py`, `tests/test_run_facts_snapshot.py` | `observedStages` follows registry order and owner presence; latest is the last present stage, never a completion claim |
| `execution.preview` / `source.preview` | Preview integrity owner | `RunFacts.preview` from `mcp.preview.integrity.inspect_preview`; never `run_status` narration | `authority-record` / `authority-record-excerpt` | No occurrence is known `absent`; the state maps only from the owner's canonical current-round confirm record, which carries the owner-computed `prototype_status`; a valid confirm whose `prototype_status` reports a prototype hash mismatch projects `invalid`, never `confirmed`; aborted/open follow owner facts; unreadable/malformed/hash mismatch cannot be upgraded to confirmed | `mcp/preview/test_integrity.py`, fixtures `g5-preview-confirmed`, `g5-only-aborted`, `g5-preview-without-confirm` | State/round equal one `PreviewSnapshot`; hash mismatch remains invalid/non-known according to the canonical confirm record's `prototype_status` |
| `execution.repair` / `source.repair-report` | repair-round and escalation owners | `parse_round_facts`, `parse_close_reason`, `parse_routes`/`route_hits`, `collect_signals`, and recorded regrades over the captured point-back/profile/DD facts | `artifact` / `artifact-excerpt` | No repair facts can be a known zero-round result; malformed/ambiguous point-back is non-known; conflicts are not reconciled | repair/escalation unit tests and point-back fixtures | Rounds, close reason, wait state, and sorted routes equal owner facts; no prose inference |
| `evaluation.evaluator` / `source.evaluator-report` | evaluator/point-back owner | `RunFacts.verdict` from `parse_verdict`, plus `parse_audit_marker`; **gate** an owner-local `PointBackProjection` for typed findings | `artifact` / `artifact-excerpt` | `audited:false` is unaudited and verdict unknown; missing/malformed/repeated verdict is `no-canonical-value`; source failures retain exact availability; findings are `owner-unmapped` until public projection exists | `pass/point-back.md`, `pass/recirculate-mentions-pass.point-back.md`, `pass/skeleton.point-back.md`, `fail/g3-*`, `test_verdict_syntax.py` | Exactly one audited canonical value maps to `Pass`/`Recirculate`; unaudited or ambiguous input never does; each finding equals owner projection |
| `evaluation.ledger` / `source.evidence-ledger` | point-back ledger/G2/G3/G4/G11 policy owners | `RunFacts.ledger` from `parse_ledger`; **gate** the same owner-local `PointBackProjection` to apply criterion outcome, proof, summary and coverage policy once | `artifact` / `artifact-excerpt` | Missing/not produced/malformed rows map to the exact reason; `n/a` maps to known `notApplicable`; invalid or duplicate rows cannot become a value | ledger syntax tests, `pass/point-back.md`, `pass/skeleton.point-back.md`, `fail/g2-*` | Criteria/coverage equal the owner projection; duplicate fields/rows and unknown L6 IDs never get silently selected |
| `evaluation.manifest` / `source.evidence-manifest` and `source.evidence-artifact.<id>` | append-only Manifest and Evidence containment/capture-contract owners | `RunFacts.manifest_entries`; `g6_records.ledger_observed`; latest-entry and policy rules in `g6_evidence.check_evidence`; `containment.read_artifact`; `validate_capture_snapshot` | `authority-record` / `authority-record-excerpt`; `artifact` / `artifact-excerpt` | Missing/unreadable/malformed entries and escaped/missing artifacts map explicitly; invalid binding yields no EvidenceBinding; multiple current bindings without an owner winner are inconsistent | fixtures `g6-evidence-bound`, `g6-multi-entry-latest`, `g6-dangling-ref`, `g6-missing-artifact`, `g6-pass-without-valid-binding` | A binding exists only for the owner-selected valid Manifest entry and contained artifact; snapshot computes `contentHash` over captured artifact bytes because current Manifest entries do not store it |
| `run.next-action` / `source.run-status` | `scripts/run_status.py` | `inspect_run` plus `next_action`; **gate** an owner-local structured `NextActionProjection` because current output is narration only | `authority-record` / `authority-record-excerpt` | Missing structured output is `owner-unmapped`; alternatives are not invented; `copyableAgentCommand` stays null unless owner output is exact | `tests/test_run_status.py`, `packages/design-playbook/tests/test_run_facts.py` | Primary/alternatives equal the structured owner result; the Console neither converts prose to commands nor executes copied text |
| `run.limitations` / `source.owner-limitations.<owner>` | owner of each limitation; deterministic build diagnostics belong to the snapshot producer | **Gate:** owner-local structured limitation emitters; producer may add only closed deterministic read/build limitations required by Snapshot v1 | owner source kind/class; build diagnostics are `authority-record` / `non-viewable` | Unmapped owner-provided limitations are `owner-unmapped`; source/build failures preserve their assertion reason and add, but are never hidden by, a limitation | later parity harness plus existing read-error tests | Every item is traceable to an owner projection or a closed build condition; no free-form Console limitation |
| `role-attestation.<owner>` / `source.role-attestation.<claim-id>` | exact semantic claim owner | **Gate:** no transaction/read seam preserving the full claim/assertion/role/authority/source-hash binding is proven | `authority-record` / `authority-record-excerpt` when mapped | Action disabled; dependent assertion uses `attestation-missing` or `owner-unmapped`; no generic confirmation file | Snapshot v1 S31-S34 future contract tests | No valid approval can appear until exact owner record round-trips every binding field |
| `diagnostic-export` | separately accepted Diagnostic export owner | **Gate:** no accepted v1 JSON/Markdown schema or transaction | no Snapshot source / `non-viewable` in read parity | Preview/write action disabled with `ACTION_UNAVAILABLE` | Snapshot v1 S35-S37 future action tests | Snapshot/Manifest/verdict stay unchanged; no export is written during read parity |

Post-acceptance note: the **gate** cells above record the 2026-08-25 state.
Four of those gates have since been satisfied through the owner-local public
read seams that section 6 condition 2 anticipates —
`g1_spec.project_specification` (specification summary and typed criteria),
`pointback_projection` (typed findings, criterion outcomes, and coverage),
`status_projection.project_next_action` (structured next action), and
`run_metadata` (package metadata, safe run identity, and structured
limitations), all under `packages/design-playbook/scripts/`. The
Role-attestation and Diagnostic-export gates remain open.

## 3. Assertion coverage matrix

The type column distinguishes fixed singleton assertions from dynamic assertion
families. Each source key is a normative foreign key to section 2, so that
row's owner seam, source kind/locator class, failure mapping, fixture, and
binary oracle are incorporated for every assertion below. “Expected parity” is
evaluated after that availability mapping.

| Assertion ID or template | Type | Source key(s) | Unique semantic owner | Owner value used by the projection | Expected parity |
| --- | --- | --- | --- | --- | --- |
| `identity.run` | static | `session.selected-run` | launch session | selected run ID and optional safe label | Equal to the selected session fact; label is null because no current safe display-label owner is proven |
| `identity.product` | static | `package.metadata` | package manifest | name and version | Exact string equality |
| `identity.profile` | static | `run.profile` | run-profile owner | declared/effective tiers and confirmation presence | Exact typed equality; human identity excluded |
| `intent.summary` | static | `intent.specification` | specification owner | owner-parsed L1 outcome summary | **Gate** until public specification projection exists |
| `intent.criteria.<criterionId>` | dynamic array | `intent.specification` | specification owner | stable ID/title/Given/When/Then | **Gate**; one assertion per owner criterion, ordered by owner order |
| `intent.contract` | static | `intent.contract` | Contract bind owner | sorted open/assumed/stale lists and blocking flag | Exact equality to `BindResult` projection |
| `execution.progress` | static | `execution.stage-registry`, `run.profile` | stage registry/status owner | stage presence and explicit skip reason | Exact registry order and values; no semantic completion inference |
| `execution.preview` | static | `execution.preview` | Preview integrity owner | current occurrence/confirm/integrity facts | Exact state and round mapping from one `PreviewSnapshot` |
| `execution.repair` | static | `execution.repair`, `run.profile` | repair/escalation owners | rounds, close reason, waiting flag, routes | Exact typed owner facts from one captured set |
| `evaluation.verdict` | static | `evaluation.evaluator` | evaluator/verdict owner | audited canonical verdict | Exact `Pass`/`Recirculate`, or exact non-known state |
| `evaluation.criteria.<criterionId>` | dynamic array | `evaluation.ledger`, `evaluation.manifest` | ledger policy owner; Manifest only binds evidence | outcome, proof, observed summary, valid bindings | **Gate** for the policy projection; Manifest cannot change outcome |
| `evaluation.findings.<findingId>` | dynamic array | `evaluation.evaluator` | point-back owner | typed finding and declared owner | **Gate**; no synthesized IDs or owner guesses |
| `evaluation.coverage` | static | `evaluation.ledger` | coverage/ledger owner | declared/reviewed/unreviewed/complete | **Gate** for one public coverage projection; counts must satisfy owner diagnostics |
| `nextActions.primary` | static | `run.next-action` | next-action owner | structured primary action | **Gate** until structured owner output exists |
| `nextActions.alternatives.<actionId>` | dynamic array | `run.next-action` | next-action owner | owner-sanctioned alternative | **Gate**; empty is known only when the owner explicitly emits an empty list |
| `limitations.items.<limitationId>` | dynamic array | `run.limitations` and affected source | limitation's semantic owner or closed build diagnostics | typed code/summary/affected IDs | Owner-local equality; **gate** for owner-provided limitations without a seam |

`identity.snapshot` and `sources` are producer metadata, not domain
assertions. They still pass parity only when the construction algorithm uses
the exact captured parser inputs and re-verifies the same registry entries.

## 4. Canonical semantic comparison

The parity harness MUST validate the full Snapshot v1 schema first, then build
two canonical semantic projections: one through owner APIs and one through the
snapshot producer. It MUST recursively sort object keys and compare UTF-8 JSON
bytes. Array order remains significant except `source.refs` and
`reason.sourceRefs`, whose contract already requires sorted uniqueness.

Only these volatile values are normalized for the final byte comparison:

| Value | Canonical treatment |
| --- | --- |
| `identity.snapshot.builtAt`, every source `observedAt`/`verifiedAt` | Replace with one `<time>` sentinel after independently checking RFC 3339 shape and ordering; nullable `verifiedAt` remains null |
| `sources.items[*].locator` | Replace each non-null locator with `<locator:{sourceRef}>` after checking opacity, uniqueness, session/run binding, and resolver behavior |

Session tokens, listener ports, filesystem roots, temporary-directory names,
stack traces, and usernames are not volatile exclusions: their presence is a
hard failure. Hashes, assertion IDs, source refs, results, reasons, approvals, read states,
freshness, `buildState`, stage/action order, and limitation text are not
volatile. They MUST compare exactly. The harness supplies a deterministic clock
and locator issuer; it does not delete unexpected fields or sort domain arrays
to manufacture equality.

## 5. Fixture catalog

The implementation workflow SHOULD compose scenario run roots from existing
fixtures and small harness-owned source doubles. This document names designs;
it creates no fixture data.

| Scenario | Seed / mutation | Required assertions | Binary parity oracle |
| --- | --- | --- | --- |
| `pass` | `pass/spec.md` + `pass/point-back.md`; add valid profile/contract/Preview/Manifest pieces as needed | known audited `Pass`; known progress; valid criterion bindings only | owner projection and canonical snapshot are byte-equal; build is current |
| `recirculate` | `pass/recirculate-mentions-pass.point-back.md` with valid spec | canonical `Recirculate`; text mentioning Pass outside Verdict is ignored | both paths return only `Recirculate`; next action is not inferred from the stray word |
| `unaudited` | `pass/skeleton.spec.md` + `pass/skeleton.point-back.md` | `evaluation.verdict` non-known; skeleton ledger rows remain explicitly unaudited/not-applicable according to owner policy | neither owner status nor snapshot yields Pass; only dependent assertions degrade |
| `missing` | omit each required source in a table-driven subcase; reuse RunFacts missing-file tests | dependent assertion is `unknown` with `not-produced` or `source-missing`; unrelated assertions unchanged | source entry/read state, reason, and affected-ID set match the owner/lifecycle classification |
| `stale` | capture complete source bytes, mutate that source before end verification | dependent assertion is `stale` with unequal hashes and `source-changed-during-build`; build degraded | no current-Pass predicate is true and no prior Console snapshot is substituted |
| `partial-write` | reader double returns a complete prefix/truncated JSON or a documented conflicting complete record during the same attempt | unparseable fact is `unknown/partial-write` (or `source-malformed` when no signature is known); conflicting complete records are `inconsistent/partial-write` | exact reason class and null-result rule hold; builder never retries into a mixed source set |
| `inconsistent-hash` | two complete current Manifest/contract/attestation records claim one semantic slot, or a cross-source invariant is intentionally violated | `inconsistent`, null result, both source refs/hashes in conflicts | no winner is selected; `conflicting-authorities` or `invariant-violation` matches owner policy |
| `malicious-locator` | issue a valid locator, then test unknown, expired, other-run, other-session, path-looking, traversal, encoded traversal, absolute, symlink escape, and hash-changed requests | snapshot semantics unchanged; resolver returns the uniform invalid-locator or hash-mismatch response | zero bytes outside the bound source are read; no path/containment detail leaks; GET remains side-effect free |

Supporting subcases reuse `mcp/preview/test_integrity.py` for malformed Preview
and hash mismatch, RunFacts tests for missing/unreadable/malformed reads,
`test_verdict_syntax.py` for ambiguous verdicts, and the G6 fixture families for
valid, missing, dangling, and superseded Manifest bindings.

## 6. Read parity gate

Typed actions stay locked until all conditions below pass in one clean test
run:

1. Every row in sections 2 and 3 is covered by a table-driven parity test.
2. Every **gate** is either satisfied by an owner-local public read seam or
   emits the specified non-known result; no snapshot/Console parser duplicates
   owner syntax.
3. All eight fixture scenarios pass owner-vs-snapshot canonical comparison and
   Snapshot v1 structural tests S01-S19, S22-S23, S26, S41, and S42.
4. Rebuilding the same immutable set is byte-equivalent after only the two
   approved volatile treatments in section 4 (the timestamp and locator
   sentinels). Changed or partial sources never reuse the
   previously served snapshot as current.
5. Locator security subcases are uniform, contained, hash-bound, and free of
   path/token/stack-trace disclosure.
6. A repository scan demonstrates zero Console writes, no telemetry or remote
   fetch, no arbitrary file editor, and no action endpoint beyond refresh and
   source resolution during this phase.

Failure of any condition blocks all write actions. UI smoke tests, manual
inspection, or a validator exit code alone cannot waive this gate.

## 7. Explicit gates for later tickets

These are the seven known gaps; they are follow-up ticket inputs, not implied
implementation inside this specification:

1. Add an owner-local Specification projection for intent summary and typed L6
   criteria.
2. Add one owner-local Point-back projection for typed criterion evaluations,
   findings, coverage, and stable domain IDs while reusing verdict/ledger/G6
   facts.
3. Add a structured next-action owner result, including explicit alternatives
   and an optional exact command; do not parse narration.
4. Decide and implement exact Role-attestation owners per normative claim, or
   keep the action disabled.
5. Accept a separate versioned Diagnostic export schema and atomic transaction,
   or keep the action disabled.
6. Add owner-local structured limitations and safe run-label/package metadata
   adapters where the current owner does not expose them.
7. Implement the session Source registry, immutable capture/re-verification
   boundary, opaque locator resolver, and the stale/partial/conflict/malicious
   parity harness.

None authorizes the Console to become a source of truth.
