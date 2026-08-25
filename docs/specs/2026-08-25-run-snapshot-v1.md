# Run Snapshot v1 domain and local Console contract

Status: implementation contract candidate. It becomes frozen when Packet 02 of
the Run Console documentation workflow is accepted.

Date: 2026-08-25.

Normative inputs:

- [Roadmap v2](../roadmap.md)
- [ADR-0035: Run View is a projection](../adr/0035-run-view-projection-authority.md)
- [ADR-0036: Diagnostic export and Role attestation](../adr/0036-invited-trial-data-and-role-boundary.md)
- [ADR-0037: local single-run Console](../adr/0037-local-single-run-console-lifecycle.md)
- [ADR-0038: snapshot contract and loopback security](../adr/0038-run-snapshot-contract-and-loopback-security.md)
- [Domain context](../../CONTEXT.md)

`MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative. Examples are
illustrative only; the rules and field tables win if an example disagrees.

## 1. Purpose and boundary

Run Snapshot v1 is the disposable, machine-facing materialization of one Run
View. It lets a local Closed-loop Run Console answer, without opening raw run
files:

1. What outcome is this run trying to deliver?
2. What is the current source verdict?
3. What blocks progress and which declaration owns the repair?
4. Who owns the next action?
5. How does each Criterion connect to its bound Artifact, Finding, and repair?

The snapshot is a deterministic projection and typed facade. It is never a
`DesignRun` aggregate, event log, decision store, Evidence store, acceptance
record, or permanent history. Refresh replaces the whole in-memory projection.
The producer MUST be able to discard and rebuild it from existing authorities.

This document defines:

- the versioned JSON domain contract;
- field and parser ownership;
- assertion availability and domain-result semantics;
- source hashing, freshness, and opaque source resolution;
- construction and rejection behavior;
- the local threat model and fixed action boundary;
- Role-attestation binding rules;
- explicit error responses and binary acceptance tests.

This document does not implement JSON Schema, fixtures, a server, UI, action
adapters, Role-attestation storage, or Diagnostic export storage. It does not
authorize a new writer. A later parity specification must bind every logical
source below to a representative current artifact and fixture before runtime
implementation begins.

## 2. Conformance roles

Four components can conform independently:

| Role | Responsibility |
| --- | --- |
| Snapshot producer | Capture one immutable source set, call existing authority parsers, and emit exactly one v1 document. |
| Snapshot consumer | Validate the complete document and render domain assertions without strengthening them. |
| Console server | Serve one selected run on loopback, resolve server-issued Source locators, and enforce request security. |
| Action adapter | Validate one allowlisted command and route it to the named existing transaction owner. |

A consumer MUST reject a non-conforming document as a whole. It MUST NOT render
the valid-looking subset of an invalid document. An assertion whose source is
missing or damaged is represented by a valid non-`known` envelope; malformed
snapshot JSON or an unsupported snapshot version is instead a contract-level
rejection.

## 3. Root object and versioning

The JSON root has one version discriminator plus exactly seven domain sections:

```json
{
  "schemaVersion": 1,
  "identity": {},
  "intent": {},
  "execution": {},
  "evaluation": {},
  "nextActions": {},
  "limitations": {},
  "sources": {}
}
```

`schemaVersion` is transport metadata, not an eighth domain section. Every key
shown above is required. Unknown root or nested keys are invalid in v1. The
eventual JSON Schema MUST use closed objects (`additionalProperties: false`) at
every fixed-shape boundary.

The only accepted snapshot version is the JSON integer `1`. The producer and
Console consumer ship in lockstep. A consumer receiving any other integer, a
string such as `"1"`, a missing version, or a version it does not implement
MUST stop before rendering and report `SNAPSHOT_VERSION_UNSUPPORTED`. It MUST
NOT try an older reader, coerce the value, show a cached older snapshot, or
silently ignore unknown fields.

Any incompatible field, enum, or semantic change requires `schemaVersion: 2`.
Long-lived backward readers are reserved for Diagnostic exports; internal Run
snapshots are rebuilt rather than migrated or archived.

## 4. Common scalar contracts

### 4.1 IDs and time

- Domain assertion IDs use lower-case dot-separated segments matching
  `^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$`.
- Source references use the same grammar with a `source.` prefix.
- IDs are unique within a snapshot. Duplicate IDs make the whole document
  invalid.
- A run ID exposed to the browser is an opaque session-scoped identifier. It
  MUST NOT be an absolute path, relative path, repository URL, username, or a
  reversible encoding of any of those values.
- Timestamps are UTC RFC 3339 strings with a `Z` suffix. They describe capture
  time only and never establish semantic authority or freshness by themselves.

Dynamic IDs for Criteria, Findings, or claims come from their authority when
one exists. If a current authority lacks an ID, the projection MAY derive one
from the authority key plus canonical semantic fields. Such an ID is a
read-only address, not a persisted identity claim.

### 4.2 Digests

All digests are strings of the form `sha256:<64 lower-case hex characters>`.

- A file content hash is SHA-256 over the exact byte sequence supplied to the
  authoritative parser. Text newline normalization is not allowed unless that
  parser's existing contract already defines it.
- A structured hash is SHA-256 over the UTF-8 bytes of RFC 8785 JSON Canonical
  Serialization Scheme output.
- A source-set hash is the structured hash of source records sorted by
  `sourceRef`, retaining only `sourceRef`, `authorityKey`, `readState`,
  `observedHash`, `verifiedHash`, and `freshness`.
- Hash comparison is exact and case-sensitive after validating the digest
  grammar.

Hashes establish byte and binding facts. They do not prove who approved a
claim, that an Artifact is Evidence, or that a semantic result is good.

## 5. Assertion envelope

Every user-meaningful fact is an `Assertion<T>`:

```json
{
  "id": "evaluation.verdict",
  "availability": "known",
  "result": "Pass",
  "reason": null,
  "source": {
    "refs": ["source.evaluator-report"],
    "observedSetHash": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
    "verifiedSetHash": "sha256:1111111111111111111111111111111111111111111111111111111111111111"
  },
  "approval": null
}
```

The fixed members are:

| Member | Contract |
| --- | --- |
| `id` | Stable domain address; unique in the snapshot. |
| `availability` | Exactly `known`, `unknown`, `stale`, or `inconsistent`. |
| `result` | The assertion's typed domain value, or `null` under the rules below. It never contains availability. |
| `reason` | `null` only for `known`; otherwise the required reason object. |
| `source` | Source references and aggregate observed/verified hashes. |
| `approval` | `null` when no role-scoped semantic confirmation is required; otherwise the Role-attestation projection. |

### 5.1 Availability and result are orthogonal

| Availability | Meaning | `result` rule |
| --- | --- | --- |
| `known` | The current, complete, supported, unambiguous source set yields one canonical value and any required attestation is valid. | Required and non-null. A legitimate domain value such as `false`, `0`, an empty list, `notApplicable`, or `absent` remains non-null and known. |
| `unknown` | No supported canonical value can currently be established. | MUST be `null`. Unknown is never rewritten as pending, false, fail, empty, or not applicable. |
| `stale` | A value was validly derived from the recorded observed hash, but an end-of-build hash or a bound source/attestation hash has changed. | MAY retain that last value solely as stale context, or be `null` when no complete value was parsed. It MUST NOT be presented as current. The value must come from the current build attempt or the authoritative record, never a previous Console snapshot. |
| `inconsistent` | Two current supported sources, records, or invariants disagree and no authority rule selects one. | MUST be `null`; conflicting candidates belong only in the reason facts. The producer MUST NOT choose a winner. |

`notApplicable` is a domain result, so it can be `known`. An absent optional
stage can likewise be the known result `absent` if an authority defines that
absence. Missing bytes, unreadable bytes, or a not-yet-produced required
artifact are `unknown` instead.

### 5.2 Reason object and closed reason codes

Every non-`known` assertion carries:

```json
{
  "code": "source-changed-during-build",
  "message": "The evaluator report changed while the snapshot was built.",
  "sourceRefs": ["source.evaluator-report"],
  "observedHashes": ["sha256:2222222222222222222222222222222222222222222222222222222222222222"],
  "verifiedHashes": ["sha256:3333333333333333333333333333333333333333333333333333333333333333"],
  "conflicts": []
}
```

All five members are required. Messages are deterministic, locally safe
explanations; they MUST NOT contain a filesystem path, token, stack trace,
credential, raw model reasoning, or unselected source text. `conflicts` is an
array of `{ "sourceRef": string, "hash": Digest|null, "summary": string }`;
`summary` describes the conflicting fact without copying raw source content.

The closed v1 reason code set is:

| Code | Normal availability | Meaning |
| --- | --- | --- |
| `not-produced` | `unknown` | The lifecycle has not produced a required authority yet. |
| `source-missing` | `unknown` | An expected authoritative source is absent. |
| `source-unreadable` | `unknown` | The source exists but a complete byte read failed. |
| `source-malformed` | `unknown` | The authority parser rejected the complete bytes. |
| `source-version-unsupported` | `unknown` | The source's own schema/version is unsupported. |
| `no-canonical-value` | `unknown` | Parsing succeeded but the owner reports no unique canonical value, including duplicate or ambiguous verdicts. |
| `dependency-unavailable` | `unknown` | A required upstream assertion is non-known. |
| `attestation-missing` | `unknown` | This semantic result requires an explicit role confirmation that is absent. |
| `owner-unmapped` | `unknown` | No existing authority owner or public read adapter is proven for the field. This is an implementation decision gate, not permission to invent one. |
| `source-changed-during-build` | `stale` | The exact bytes parsed differ from the bytes verified at the end of construction. |
| `attestation-invalidated` | `stale` | A previously bound claim or authoritative source hash changed. |
| `partial-write` | `unknown` or `inconsistent` | A source exposes a documented partial-write signature. Use `unknown` if nothing complete parses; use `inconsistent` if complete current records conflict. |
| `conflicting-authorities` | `inconsistent` | Multiple current records claim the same semantic slot and the existing owner does not choose one. |
| `invariant-violation` | `inconsistent` | Individually readable current facts violate an existing deterministic cross-source invariant. |

No generic `other` code exists. Adding a reason requires a new snapshot schema
version or an accepted compatible-contract decision.

### 5.3 Assertion source binding

`source.refs` is a sorted, unique, non-empty list of entries present in
`sources.items`. `observedSetHash` hashes the bytes or structured facts used to
derive the result; it is nullable only when no source bytes could be captured.
`verifiedSetHash` hashes the end-of-build verification state; it is nullable
only when verification itself is impossible. For `known`, both hashes are
required and equal. A hash mismatch requires `stale` or `inconsistent`; it can
never remain `known`.

## 6. Role-attestation projection

Only assertions whose downstream acceptance depends on human product, design,
or engineering judgment carry a non-null `approval`:

```json
{
  "claimId": "claim.intent.checkout-safety",
  "claimHash": "sha256:4444444444444444444444444444444444444444444444444444444444444444",
  "requiredRole": "product",
  "authorityKey": "intent.contract",
  "sourceRef": "source.intent-contract",
  "sourceHash": "sha256:5555555555555555555555555555555555555555555555555555555555555555",
  "state": "missing",
  "attestationId": null
}
```

The rules are:

1. `requiredRole` is exactly `product`, `design`, or `engineering`.
2. `claimId` is stable in its existing authority. `claimHash` is the structured
   hash of the claim ID, assertion ID, role, and exact proposed semantic value.
3. `sourceHash` is the current hash of the authoritative source containing the
   claim. A Source locator is session-scoped and MUST NOT be persisted as the
   claim identity.
4. `state` is exactly `missing`, `valid`, or `invalidated`. A valid state
   requires an attestation bound to the exact claim ID, claim hash, role,
   authority key, and source hash.
5. `attestationId` is non-null only for `valid` or `invalidated` records that
   actually exist.
6. A missing attestation makes only its dependent assertion `unknown` with
   `attestation-missing`. It does not block unrelated assertions or create a
   global three-role gate.
7. A changed claim or source hash makes the dependent assertion `stale` with
   `attestation-invalidated`; the prior attestation cannot be reused.
8. Attestations do not inherit between roles. The same person acting in two
   roles must submit two separately bound confirmations.
9. The record scopes semantic authority but proves no identity, employment,
   organization membership, entitlement, or legal consent.
10. An Agent, workflow continuation, Run operator action, or earlier role click
    can never synthesize a valid attestation.

If the parity work cannot name an existing transaction owner capable of
persisting this exact binding, Role-attestation actions remain disabled and a
limitation with `owner-unmapped` is shown. Implementers MUST NOT add a generic
confirmation file or Console-owned approval store.

## 7. Seven domain sections

Every fixed field below is required even when its assertion is non-known or its
array is empty. Dynamic assertion arrays are sorted by assertion ID.

### 7.1 `identity`

| Field | Result type and meaning |
| --- | --- |
| `snapshot` | Non-assertion build metadata: `{ "builtAt": Timestamp, "sourceSetHash": Digest, "buildState": "current"|"degraded" }`. `current` requires every source used by a known assertion to verify unchanged; any non-known assertion or changed source makes it `degraded`. |
| `run` | `Assertion<{ "runId": string, "label": string|null }>` for the one explicitly selected run. `label` is null unless an existing safe display label exists. |
| `product` | `Assertion<{ "name": "design-playbook", "version": string }>` from installed package metadata. |
| `profile` | `Assertion<{ "declaredTier": "P1"|"P2"|"P3"|null, "effectiveTier": "P1"|"P2"|"P3"|null, "confirmedBy": "human"|null }>` from the run-profile authority. It never exposes a person's name. |

The absolute selected run root remains server-side. `runId` identifies the
session context only and is not a new durable run ID.

### 7.2 `intent`

| Field | Result type and meaning |
| --- | --- |
| `summary` | `Assertion<string>` containing the owner-parsed outcome summary, not a model-generated summary. |
| `criteria` | Array of `Assertion<Criterion>`, one per authoritative L6 Criterion. `Criterion` is `{ "criterionId": string, "title": string|null, "given": string, "when": string, "then": string }`. |
| `contract` | `Assertion<{ "openFields": string[], "assumedFields": string[], "staleFields": string[], "blocking": boolean }>` from the persistent-contract bind authority when applicable. Field paths are domain paths, not filesystem paths. |

The producer MUST NOT summarize intent from source code, a README, Agent
reasoning, or a prior snapshot when the run declaration is unavailable.

### 7.3 `execution`

| Field | Result type and meaning |
| --- | --- |
| `progress` | `Assertion<{ "observedStages": Stage[], "latestObservedStage": string|null }>` where `Stage` is `{ "stageId": string, "label": string, "presence": "present"|"absent"|"skipped", "skipReason": string|null }`. Presence does not claim semantic completion. |
| `preview` | `Assertion<{ "state": "absent"|"open"|"confirmed"|"aborted"|"invalid", "round": integer|null }>` projected only through Preview integrity and transaction facts. |
| `repair` | `Assertion<{ "rounds": integer, "closeReason": "pass"|"escalated-stop"|"aborted"|null, "waitingForHuman": boolean, "routes": string[] }>` from repair-round and escalation authorities. |

Internal G-number gate names, lock names, filenames, and adapter-specific state
MUST NOT appear as public progress fields.

### 7.4 `evaluation`

| Field | Result type and meaning |
| --- | --- |
| `verdict` | `Assertion<"Pass"|"Recirculate">`. Anything other than one canonical owner-parsed verdict is non-known. An unaudited skeleton cannot yield a known verdict. |
| `criteria` | Array of `Assertion<CriterionEvaluation>`, where the result is `{ "criterionId": string, "outcome": "pass"|"fail"|"blocked"|"notApplicable", "requiredProof": string, "observedSummary": string, "evidenceBindings": EvidenceBinding[] }`. |
| `findings` | Array of `Assertion<Finding>`, where the result is `{ "findingId": string, "criterionIds": string[], "issue": string, "severity": "S3"|"S2"|"S1"|"S0", "disposition": "blocking"|"advisory"|"info", "owner": FindingOwner, "repair": string }`. |
| `coverage` | `Assertion<{ "declared": integer, "reviewed": integer, "unreviewed": integer, "complete": boolean }>` from existing coverage and ledger facts. |

`EvidenceBinding` is `{ "artifactId": string, "sourceRef": string,
"contentHash": Digest }`. It exists only when the Manifest authority binds the
Artifact to that Criterion. A provider output without a valid Manifest binding
is not projected as Evidence.

`FindingOwner` is `{ "kind": "declaration"|"artifact"|"decision"|"unknown",
"domainId": string|null, "sourceRef": string|null }`. When the point-back
owner cannot be parsed, the Finding assertion is non-known; the producer does
not invent an owner from the repair text.

Criterion outcome and assertion availability remain separate. For example, a
stale criterion may retain `outcome: "pass"` as stale context; this is never a
current pass. An outcome of `notApplicable` can be current and known.

### 7.5 `nextActions`

| Field | Result type and meaning |
| --- | --- |
| `primary` | `Assertion<NextAction>` for the existing next-action resolver's canonical primary result. |
| `alternatives` | Array of `Assertion<NextAction>` for owner-sanctioned alternatives. Empty means no alternatives; it does not mean the primary is known. |

`NextAction` is:

```json
{
  "actionId": "action.stop-after-pass",
  "kind": "stop",
  "label": "Run complete. Stop or begin a different run.",
  "owner": { "actor": "run-operator", "role": null },
  "copyableAgentCommand": null
}
```

`kind` is `agent-command`, `human-decision`, `source-review`, `continue`, or
`stop`. `actor` is `run-operator`, `semantic-approver`, `agent`, or
`validator`; `role` is null or one of the three semantic roles.
`copyableAgentCommand` is non-null only when an existing owner produces one
exact command string. Prose narration MUST NOT be transformed into an
executable command. Copying never executes the command.

### 7.6 `limitations`

`items` is an array of `Assertion<Limitation>`, where `Limitation` is:

```json
{
  "code": "role-attestation-owner-unmapped",
  "summary": "Role attestation is unavailable until an existing owner is mapped.",
  "affectsAssertionIds": ["intent.summary"]
}
```

Limitations include owner-provided run limitations and deterministic Console
limits that materially affect interpretation. They do not hide source errors;
the affected assertion remains non-known as well. The producer MUST surface at
least these conditions when present: unreadable source, changed-during-build
source, unsupported source version, unmapped authority owner, unavailable
Role-attestation adapter, and unavailable Diagnostic export contract.

### 7.7 `sources`

```json
{
  "sourceSetHash": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "items": [
    {
      "sourceRef": "source.evaluator-report",
      "authorityKey": "evaluation.evaluator",
      "kind": "artifact",
      "locator": "src_AQIDBAUGBwgJCgsMDQ4PEA",
      "readState": "complete",
      "observedHash": "sha256:7777777777777777777777777777777777777777777777777777777777777777",
      "verifiedHash": "sha256:7777777777777777777777777777777777777777777777777777777777777777",
      "freshness": "current",
      "observedAt": "2026-08-25T08:00:00Z",
      "verifiedAt": "2026-08-25T08:00:00Z"
    }
  ]
}
```

`items` is sorted by `sourceRef`; references are unique. Fixed fields and enums:

- `authorityKey` names a semantic owner from the registry below, not a file.
- `kind` is `artifact`, `authority-record`, `package`, or `session-selection`.
- `locator` is an opaque session-issued locator or null for a non-viewable
  source. It never contains or encodes a path.
- `readState` is `complete`, `missing`, `unreadable`, `malformed`, or
  `unsupported`.
- `freshness` is `current`, `changed`, or `unverified`.
- `observedHash` hashes the exact captured input; `verifiedHash` hashes the
  end-of-build bytes. Either can be null only when its read did not complete.
- `observedAt` is always present; `verifiedAt` is nullable only when
  verification did not complete.

No source entry exposes raw file names, paths, symlink targets, usernames,
repository roots, lock metadata, stack traces, or source text.

## 8. Authority registry and field ownership

Snapshot code consumes existing parsers and transactions; it does not duplicate
their regexes or reinterpret their outputs. Current file/module names below are
implementation evidence, not browser API fields.

| Authority key | Snapshot fields | Existing owner boundary | Write rule |
| --- | --- | --- | --- |
| `session.selected-run` | `identity.run` | Explicit Console launch selection and canonical containment of one run root. | Session-only; never persisted as run semantics. |
| `package.metadata` | `identity.product` | Installed package metadata. | Read-only. |
| `run.profile` | `identity.profile` | `run_profile.py` through the immutable `RunFacts` capture. | Existing run-profile confirmation owner only. |
| `intent.specification` | `intent.summary`, `intent.criteria` | `g1_spec.py` owns L1-L6 shape; implementation must add/use an owner-local public projection rather than copy its private parsing. | Existing specification/contract workflow only. |
| `intent.contract` | `intent.contract` and affected approvals | `contract_v1.py`, the run bind record, and G7 contract-drift authority. | Existing Contract and append-only Decision transaction only. |
| `execution.stage-registry` | `execution.progress` | `stages.py` plus `run_status.inspect_run`, over one immutable `RunFacts`. | Read-only projection. |
| `execution.preview` | `execution.preview` | Preview `integrity.py` and `transaction.py`; `run_status` may narrate but cannot redefine confirmation. | Preview transaction only. |
| `execution.repair` | `execution.repair` | `repair_rounds.py`, `escalation_signals.py`, and current decision/report parsers over `RunFacts`. | Existing run artifact owners only. |
| `evaluation.evaluator` | `evaluation.verdict`, `evaluation.findings` | `verdict_syntax.py`, `audit_preferences.py`, `g2_g4_pointback.py`, and `validate_run.py` diagnostics. | Evaluator/point-back owner only. |
| `evaluation.ledger` | `evaluation.criteria`, `evaluation.coverage` | Evidence ledger syntax plus G2/G3/G4/G11 policy. | Evaluator/ledger owner only. |
| `evaluation.manifest` | `evidenceBindings` | `RunFacts` manifest capture plus G6 and Evidence containment/capture-contract authorities. | Existing append-only Manifest owner only. |
| `run.next-action` | `nextActions` | `run_status.next_action` and owner-local structured adapters. | Read-only; copied commands are never executed by the Console. |
| `run.limitations` | `limitations` | Owner-provided limitations plus deterministic read/build diagnostics. | Read-only projection. |
| `role-attestation.<owner>` | `approval` | Must be mapped by parity work to the existing owner of the exact normative claim. | Disabled if no exact owner exists; never a Console-owned generic file. |
| `diagnostic-export` | Export action only | Separately versioned Diagnostic export transaction accepted under ADR-0036. | Writes only under the selected run's `trial-export/`; never Evidence or acceptance input. |

When an owner has no public read adapter, implementation may deepen that owner
with a narrow read-only function. It MUST NOT fork syntax into the Snapshot
module. If the owner or precedence is still unclear after parity work, emit
`owner-unmapped` and block the dependent implementation ticket.

## 9. Snapshot construction and freshness

One refresh performs exactly one full build attempt:

1. Accept one explicitly selected run root from server launch state. Resolve it
   canonically once and keep the resolved value server-side.
2. Instantiate the server-side logical-source registry for that run. Browser
   input cannot add a source or a path.
3. Capture complete bytes or immutable structured facts for every source needed
   by the registry. Compute each `observedHash` over the exact parser input.
4. Invoke the existing authority parsers over that captured source set. A
   parser must not re-open a newer version behind the capture boundary.
5. Build domain assertions without inferring stronger semantics.
6. Re-read or otherwise re-verify every captured source at the end of the same
   attempt and compute `verifiedHash`.
7. Mark changed, missing, unreadable, partial, conflicting, and unsupported
   facts according to this contract. Compute the source-set hash and return the
   entire snapshot atomically to the consumer.

The producer MUST NOT incrementally mutate an earlier snapshot, fill missing
fields from a prior successful build, or label a mixed-time value current.
There is no automatic hidden retry in v1: a changed source is observable as
`stale`/`degraded`, and the operator may explicitly refresh again. This keeps
tests and error timing deterministic.

A source that is parseable on the first read but changes before verification
may leave its parsed result only as `stale`. A partial write that does not parse
is `unknown`; complete conflicting records are `inconsistent`. A source that
remains byte-stable can still be inconsistent with another stable source when
an existing cross-source invariant fails.

Snapshots live only in the active process memory. The server MAY replace the
current in-memory snapshot after a successful build response, but it MUST NOT
write a snapshot archive. A build-level fatal error leaves no newly current
snapshot; the consumer shows the explicit error and does not fall back.

For semantic-drift tests, compare canonical snapshots after removing only
`identity.snapshot.builtAt`, source observation/verification timestamps, opaque
run IDs, and Source locators. Results, availability, reason codes, approvals,
source hashes, source refs, and owner keys remain comparison material.

## 10. Source locator and read-only resolution

A Source locator is issued only by the active server while building the source
registry. It is an opaque, high-entropy, base64url token prefixed `src_`. Its
server-side entry binds:

- the active session;
- the one selected run;
- one allowlisted logical source and canonical contained target;
- an optional authority-defined semantic anchor;
- the source hash observed for the snapshot.

The browser receives only the token. It cannot supply a path, alter an anchor,
choose an encoding, request a byte range, or ask the server to open an editor.
Locators expire when the server session ends and are invalid in every other run
or session.

The read endpoint is:

```text
GET /api/v1/sources/{locator}?expectedHash=sha256:<hex>
```

It requires the session token and request checks in section 11. The server
looks up the locator; it never interprets the token as a path. It then resolves
the already-bound target canonically inside the selected run root, rejects
symlink or traversal escape, re-hashes the complete source, and requires exact
equality with `expectedHash` and the locator's bound hash.

Success returns:

```json
{
  "schemaVersion": 1,
  "sourceRef": "source.evaluator-report",
  "sourceHash": "sha256:7777777777777777777777777777777777777777777777777777777777777777",
  "anchor": { "kind": "semantic", "label": "Verdict" },
  "mediaType": "text/plain; charset=utf-8",
  "excerpt": "Pass",
  "truncated": false
}
```

The excerpt is server-rendered, bounded, UTF-8 plain text with control
characters removed and HTML escaped by the consumer. The anchor is selected by
the authority adapter. The response does not include a path, URI, source-map
offset, editor command, surrounding arbitrary file contents, or executable
markup. Hash mismatch fails with `SOURCE_HASH_MISMATCH`; it never returns a
newer excerpt under an older binding.

## 11. Loopback threat model and request security

### 11.1 Threats in scope

The Console assumes a malicious or compromised local Web page, DNS rebinding,
cross-site requests, guessed endpoints, stale tabs, malicious locator/action
payloads, local concurrent source writers, HTML/script content inside run
artifacts, and accidental disclosure through URLs or errors. Loopback binding
reduces network exposure but is not authentication.

Operating-system account compromise, a process that can read the Console
process memory, and malicious code already running with equal filesystem access
are outside v1's authentication claim. The Console still fails closed and does
not broaden those processes' file access.

### 11.2 Session and transport rules

1. Bind an ephemeral port to an IP-literal loopback address only (`127.0.0.1`
   or `[::1]`), never `0.0.0.0`, a LAN address, hostname wildcard, Unix socket
   proxy, or remote tunnel.
2. Generate at least 256 bits of cryptographically secure random session-token
   entropy for every server lifetime. Never reuse or persist the token.
3. API requests carry `Authorization: Bearer <token>`. The token MUST NOT appear
   in a query string, cookie, response body, access log, error, or snapshot.
   Browser launch MAY pass it in the URL fragment; the fragment must be removed
   from history immediately and retained only in page memory.
4. Validate the `Host` header against the exact bound loopback origin. For every
   non-GET/HEAD request, require `Origin` to equal that exact origin. Reject
   missing, `null`, wildcard, file, extension, remote, or alternate-port
   origins. For GET/HEAD, reject a supplied conflicting Origin.
5. Do not enable CORS. Responses use a restrictive Content Security Policy,
   `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, and
   `Cache-Control: no-store`.
6. Every API route, including snapshot and source reads, requires the token.
   Token comparison is constant-time after basic length/encoding validation.
7. GET and HEAD are side-effect-free. HEAD returns the same status and headers
   as GET without a body. No GET/HEAD request writes files, attestations,
   exports, snapshots, logs under the run, or clipboard content.
8. Non-GET action requests require `Content-Type: application/json`, a bounded
   body, a fixed closed payload schema, the token, and exact Origin. Unknown
   action names or fields are rejected.
9. Artifact text is data, never HTML. Excerpts and error messages are escaped;
   the server never serves arbitrary run files as executable content.
10. The server performs no telemetry, upload, remote fetch, account lookup,
    machine fingerprinting, or network discovery.

Closing the session invalidates the token and every Source locator and stops
serving. A future persistent or remote service requires a separate security and
lifecycle decision.

## 12. Fixed v1 operations and action allowlist

There is no generic `/mutate`, `/run`, `/command`, file-write, or arbitrary
action endpoint. Only the operations below may exist.

### 12.1 Snapshot read and refresh

- `GET /api/v1/snapshot` returns the current full snapshot or builds one if the
  session has none. It never returns an older snapshot after a failed rebuild.
- `POST /api/v1/actions/refresh` accepts exactly `{ "schemaVersion": 1,
  "action": "refresh" }`. It performs a full rebuild and returns that snapshot.
  It does not write domain authority.

### 12.2 Resolve/view an authority source

Source resolution uses the GET contract in section 10. It is read-only and
hash-bound. It never launches an editor or returns raw file access.

### 12.3 Copy the next Agent command

Copying is a browser-only operation initiated by a human user gesture. It may
copy only the exact non-null `copyableAgentCommand` from a `known` NextAction.
There is no server execution endpoint. An unknown, stale, inconsistent, null,
or prose-derived command disables copy. The Console never executes, schedules,
or auto-runs the command.

### 12.4 Request a Role attestation

The endpoint, when and only when an exact existing authority owner is mapped,
is `POST /api/v1/actions/role-attestation`. The closed request is:

```json
{
  "schemaVersion": 1,
  "action": "role-attestation",
  "expectedSourceSetHash": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "assertionId": "intent.summary",
  "claimId": "claim.intent.checkout-safety",
  "claimHash": "sha256:4444444444444444444444444444444444444444444444444444444444444444",
  "role": "product",
  "authorityKey": "intent.contract",
  "sourceRef": "source.intent-contract",
  "sourceHash": "sha256:5555555555555555555555555555555555555555555555555555555555555555",
  "decision": "confirm"
}
```

The server re-resolves the assertion, claim, role, authority owner, and current
source hash from authoritative state. Every supplied binding must match. Only a
human's explicit `decision: "confirm"` submission may invoke the owner's
transaction. The adapter passes the binding fields; it cannot translate them
into a blanket approval. On success, it performs a full snapshot rebuild and
returns the rebuilt snapshot. Any changed binding fails
`CLAIM_BINDING_STALE`, writes nothing, and requires refresh.

This action remains absent or explicitly unavailable until parity work proves
the owner. The Console MUST NOT implement a temporary confirmation store.

### 12.5 Generate a Diagnostic export

Diagnostic export is one typed transaction with a preview and a write phase:

1. `POST /api/v1/actions/diagnostic-export/preview` validates a separately
   versioned Diagnostic export request and returns the exact candidate JSON and
   Markdown plus a `previewHash`; it writes nothing.
2. After explicit participant review,
   `POST /api/v1/actions/diagnostic-export/write` requires the same
   `expectedSourceSetHash`, export request, and `previewHash`. It atomically
   writes only the accepted JSON and Markdown under the selected run's
   `trial-export/` subtree, then performs a full snapshot rebuild.

Both payloads are closed schemas and require section 11 protections. The action
MUST remain disabled until the separate Diagnostic export schema is accepted;
this snapshot contract does not authorize an ad-hoc export payload. Export
never writes under `evidence/`, never updates a Manifest, never changes a
verdict, never uploads, and never counts as acceptance.

### 12.6 Forbidden actions

The Console MUST NOT execute a repair, rerun an Agent, invoke a Provider,
change a Contract, append arbitrary reasoning, edit a file, alter Evidence or a
Manifest, choose a verdict, write acceptance, infer an attestation, publish,
release, upload, or call an arbitrary command. Adding any operation requires an
explicit allowlist decision naming its transaction owner and threat expansion.

## 13. Error contract

Every API failure returns JSON and performs no partial success:

```json
{
  "schemaVersion": 1,
  "error": {
    "code": "SOURCE_HASH_MISMATCH",
    "message": "The authority source changed. Refresh before viewing it.",
    "requestId": "req_Fp3x9Jk2",
    "retryable": true
  }
}
```

The four error members are required and no other member is allowed. Messages
are safe and contain no path, token, source text, traceback, or credential.
`requestId` is ephemeral and not written into the run.

| HTTP | Code | Required behavior |
| --- | --- | --- |
| 400 | `MALFORMED_JSON` | Reject before action dispatch. |
| 400 | `ACTION_PAYLOAD_INVALID` | Reject missing, mistyped, oversized, or unknown fields. |
| 401 | `SESSION_TOKEN_INVALID` | Return the same response for missing, malformed, expired, or wrong tokens. |
| 403 | `ORIGIN_INVALID` | Reject Host/Origin policy failure. |
| 404 | `SOURCE_LOCATOR_INVALID` | Use the same response for unknown, expired, cross-run, escaped, or disallowed locators. |
| 405 | `METHOD_NOT_ALLOWED` | Reject methods outside the exact route contract; include an accurate `Allow` header. |
| 409 | `SNAPSHOT_HASH_MISMATCH` | Client action references a snapshot other than the current served snapshot. |
| 409 | `SOURCE_HASH_MISMATCH` | Locator/request hash no longer matches current bytes. |
| 409 | `CLAIM_BINDING_STALE` | Claim, role, authority, assertion, or source binding changed. |
| 409 | `ACTION_UNAVAILABLE` | The exact existing owner or separately accepted contract is not enabled. |
| 413 | `REQUEST_TOO_LARGE` | Reject before JSON parsing beyond the configured bound. |
| 415 | `CONTENT_TYPE_UNSUPPORTED` | Reject action bodies other than JSON. |
| 422 | `SNAPSHOT_VERSION_UNSUPPORTED` | Producer/consumer/action version is unknown; do not downgrade. |
| 422 | `SNAPSHOT_CONTRACT_INVALID` | Full snapshot fails shape or invariant validation; render none of it. |
| 500 | `SOURCE_READ_FAILED` | Required source capture or verification failed outside a representable assertion-local condition. |
| 500 | `AUTHORITY_OWNER_FAILED` | Named transaction owner failed; do not report success or rebuild as if it wrote. |
| 500 | `EXPORT_WRITE_FAILED` | Export transaction failed atomically; report no generated export. |
| 500 | `SNAPSHOT_BUILD_FAILED` | Unexpected build failure; never serve the previous snapshot as current. |

An assertion-local missing or malformed source normally produces a valid
degraded snapshot. A root containment failure, invalid selected run, internal
contract bug, or inability to construct a coherent seven-section document is a
request-level error instead.

## 14. Contract invariants

All conforming implementations preserve these invariants:

1. One session projects exactly one explicitly selected run.
2. Every domain assertion is rebuildable from its named existing authority.
3. The snapshot owns no decision, confirmation, Evidence, Finding, verdict, or
   acceptance state.
4. Domain result and availability are never collapsed into one status.
5. A `known` assertion has equal observed and verified source-set hashes.
6. Unknown never means pending, false, fail, empty, or not applicable.
7. Stale data is visibly stale and never comes from a previous Console
   snapshot.
8. Inconsistent sources never produce a chosen result.
9. Source paths and raw artifact topology never cross the browser contract.
10. Source locators are opaque, session/run scoped, allowlisted, contained,
    hash-bound, and read-only.
11. Required Role attestation is claim-, role-, authority-, and source-bound;
    it neither transfers across roles nor proves identity.
12. Missing attestation blocks only the dependent assertion.
13. Every write routes to the one named existing transaction owner or is
    rejected as unavailable.
14. GET and HEAD have no side effects; copy never executes; no generic mutation
    route exists.
15. A completed typed action triggers a full rebuild, not an in-place snapshot
    patch.
16. Unknown versions, invalid hashes, invalid locators, invalid origins, and
    invalid payloads fail closed without compatibility fallback or mock success.
17. Snapshot construction, viewing, and actions perform no hidden telemetry or
    upload.
18. Snapshots are disposable. Only a separately accepted Diagnostic export is
    a persistent new trial record, and it is neither Evidence nor acceptance.

## 15. Examples

### 15.1 Known verdict

```json
{
  "id": "evaluation.verdict",
  "availability": "known",
  "result": "Pass",
  "reason": null,
  "source": {
    "refs": ["source.evaluator-report"],
    "observedSetHash": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
    "verifiedSetHash": "sha256:1111111111111111111111111111111111111111111111111111111111111111"
  },
  "approval": null
}
```

### 15.2 Stale pass is not a current pass

```json
{
  "id": "evaluation.verdict",
  "availability": "stale",
  "result": "Pass",
  "reason": {
    "code": "source-changed-during-build",
    "message": "The evaluator report changed while the snapshot was built.",
    "sourceRefs": ["source.evaluator-report"],
    "observedHashes": ["sha256:2222222222222222222222222222222222222222222222222222222222222222"],
    "verifiedHashes": ["sha256:3333333333333333333333333333333333333333333333333333333333333333"],
    "conflicts": []
  },
  "source": {
    "refs": ["source.evaluator-report"],
    "observedSetHash": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
    "verifiedSetHash": "sha256:3333333333333333333333333333333333333333333333333333333333333333"
  },
  "approval": null
}
```

### 15.3 Missing Role attestation blocks one claim

```json
{
  "id": "intent.summary",
  "availability": "unknown",
  "result": null,
  "reason": {
    "code": "attestation-missing",
    "message": "Product-role confirmation is required for this claim.",
    "sourceRefs": ["source.intent-contract"],
    "observedHashes": ["sha256:5555555555555555555555555555555555555555555555555555555555555555"],
    "verifiedHashes": ["sha256:5555555555555555555555555555555555555555555555555555555555555555"],
    "conflicts": []
  },
  "source": {
    "refs": ["source.intent-contract"],
    "observedSetHash": "sha256:5555555555555555555555555555555555555555555555555555555555555555",
    "verifiedSetHash": "sha256:5555555555555555555555555555555555555555555555555555555555555555"
  },
  "approval": {
    "claimId": "claim.intent.checkout-safety",
    "claimHash": "sha256:4444444444444444444444444444444444444444444444444444444444444444",
    "requiredRole": "product",
    "authorityKey": "intent.contract",
    "sourceRef": "source.intent-contract",
    "sourceHash": "sha256:5555555555555555555555555555555555555555555555555555555555555555",
    "state": "missing",
    "attestationId": null
  }
}
```

Other assertions whose result does not depend on this claim remain known when
their own sources support them.

## 16. Binary acceptance tests

Each row is a mandatory yes/no test. A failure blocks read parity or the action
phase named by the test.

| ID | Given / when | Pass condition |
| --- | --- | --- |
| S01 | A producer emits v1. | Root has integer version 1 and exactly the seven required domain sections; every fixed object is closed. |
| S02 | Version is missing, a string, 0, or 2. | Consumer renders no assertion and returns `SNAPSHOT_VERSION_UNSUPPORTED`. |
| S03 | A required or unknown field appears at any fixed boundary. | Consumer rejects the whole document with `SNAPSHOT_CONTRACT_INVALID`. |
| S04 | Two assertions or sources share an ID/ref. | Whole document is rejected. |
| S05 | A known assertion has null result, non-null reason, missing source, or unequal hashes. | Whole document is rejected. |
| S06 | An unknown assertion contains a non-null result. | Whole document is rejected. |
| S07 | A stale verdict retains `Pass` with unequal observed/verified hashes. | It is displayed only as stale context and cannot satisfy a current-Pass check. |
| S08 | Current sources conflict. | Availability is inconsistent, result is null, conflicts name the source refs, and no winner is chosen. |
| S09 | A conditional gate did not apply and its authority reports `notApplicable`. | Result is known `notApplicable`, not unknown or pass. |
| S10 | A required artifact has not yet been produced. | Dependent assertion is unknown with `not-produced`; unrelated assertions retain their own availability. |
| S11 | Current owner parser reports duplicate/malformed verdict text. | Verdict is unknown with `no-canonical-value`; no permissive regex yields Pass. |
| S12 | Same immutable source set is rebuilt twice. | Canonical semantic snapshots, after removing only approved volatile fields, are byte-equivalent. |
| S13 | A parsed source changes before end verification. | Its dependent assertions are stale, snapshot is degraded, and neither build is labeled current. |
| S14 | A file is observed during a documented partial write and cannot parse. | Assertion is unknown with `partial-write` or `source-malformed`; the prior snapshot is not substituted. |
| S15 | Two complete current records violate an existing invariant. | Assertion is inconsistent with source hashes and no selected result. |
| S16 | A build fails after a previous successful refresh. | API returns the explicit build error; it does not return the old snapshot as current. |
| S17 | Every projected field is checked against the parity map. | Each field names exactly one authority/parser path or an explicit `owner-unmapped` decision gate; no duplicated parser exists. |
| S18 | A provider-created Artifact lacks a valid Manifest Criterion binding. | It is not projected as Evidence. |
| S19 | Snapshot and errors are scanned for path forms, selected-root text, usernames, tokens, and stack traces. | None are present. |
| S20 | A valid locator is resolved with its bound hash. | Response is a bounded read-only semantic excerpt with no path or executable markup. |
| S21 | Locator contains traversal/path text, is random, expired, cross-session, cross-run, or resolves through an escape. | Same `SOURCE_LOCATOR_INVALID` response, no file bytes returned. |
| S22 | Valid locator uses a stale expected hash. | `SOURCE_HASH_MISMATCH`; no newer excerpt is returned. |
| S23 | Source content contains HTML/script. | It is returned/rendered as escaped text; no script executes. |
| S24 | Server binding is inspected. | It listens only on one IP-literal loopback address and one ephemeral port. |
| S25 | Token is missing, wrong, expired, in a query, or reused after close. | Request fails with `SESSION_TOKEN_INVALID`; token never appears in response/log/run files. |
| S26 | Host or action Origin differs by host, scheme, or port, or Origin is null/missing. | Request fails with `ORIGIN_INVALID` and performs no action. |
| S27 | Filesystem and owner records are snapshotted before and after every GET/HEAD route. | They are identical; HEAD has no body. |
| S28 | Action body is non-JSON, oversized, has an unknown action, unknown field, wrong type, or wrong version. | Fixed 4xx error and zero owner calls/writes. |
| S29 | User copies a known next Agent command. | Clipboard receives exactly the snapshot string; no process, Agent, command, or network request is executed. |
| S30 | Copy target is prose-derived, null, unknown, stale, or inconsistent. | Copy is disabled and no fallback command is synthesized. |
| S31 | Role-attestation request matches assertion, claim, role, owner, current source, and snapshot hashes. | Exactly one named owner transaction runs after explicit human submit, then a full snapshot rebuild occurs. |
| S32 | Any Role-attestation binding changed or a different role reuses a record. | `CLAIM_BINDING_STALE`, zero writes, and no cross-role confirmation. |
| S33 | Required attestation is missing. | Only dependent assertions are unknown; no global three-role gate appears. |
| S34 | No exact Role-attestation owner is mapped. | Endpoint is absent/unavailable, limitation is visible, and no Console confirmation file is created. |
| S35 | Diagnostic export schema is not separately accepted/enabled. | Preview/write actions return `ACTION_UNAVAILABLE`; no ad-hoc export is written. |
| S36 | Export preview is accepted, then source set or preview content changes before write. | Write is rejected; no partial JSON/Markdown pair exists. |
| S37 | Export write succeeds. | Only an atomic JSON/Markdown pair appears under `trial-export/`; `evidence/`, Manifest, verdict, and acceptance facts are unchanged; full rebuild follows. |
| S38 | Every completed typed write action is observed. | It calls only the named owner and returns a full rebuild; no in-place snapshot patch or dual write occurs. |
| S39 | Forbidden repair, rerun, arbitrary path, acceptance, upload, or command-execution requests are attempted. | No route exists or `METHOD_NOT_ALLOWED`/`ACTION_PAYLOAD_INVALID` is returned; zero effects. |
| S40 | Network calls are recorded during snapshot, source view, and actions. | No telemetry, upload, remote fetch, account lookup, or fingerprinting occurs. |
| S41 | Two runs exist and the Console is launched for one. | Snapshot, locators, actions, and source excerpts contain only the selected run; no aggregate or ranking appears. |
| S42 | Fifty unchanged-source rebuilds run against parity fixtures. | Zero semantic drift under the canonical comparison; any mismatch fails the graduation gate. |

The read-only Console cannot leave its phase until S01-S30, S39-S42, and the
separate parity fixtures pass. Role-attestation requires S31-S34. Diagnostic
export requires S35-S37 plus its separately accepted schema. No action phase
may use a green UI smoke test as a substitute for these contract checks.

## 17. Explicit implementation gates

The following are deliberate gates rather than implied compatibility behavior:

- Packet 03 must map every authority key and dynamic assertion to current
  parser inputs/outputs and define parity fixtures. If an owner has no public
  read seam, add the seam at that owner; do not duplicate parsing in Console
  code.
- Role attestation remains unavailable until a current authority transaction
  can preserve the exact binding in section 6. If none exists, an additional
  architecture decision is required before writing code.
- Diagnostic export remains unavailable until its own minimal, reviewable,
  versioned JSON/Markdown contract is accepted. Snapshot v1 does not fill that
  missing schema.
- A structured copyable Agent command remains null until an existing
  next-action owner emits an exact command. Converting narration to a command
  is forbidden.
- Remote access, persistence, multiple active runs, automatic repair/rerun,
  arbitrary file editing, generic mutation, and hidden telemetry require new
  decisions and are not v1 extensions.

These gates ensure an implementation agent never resolves an unknown by
creating a second source of truth or a silent fallback.
