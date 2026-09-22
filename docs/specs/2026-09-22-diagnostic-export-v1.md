# Diagnostic export contract v1

Status: accepted ([ADR-0044](../adr/0044-diagnostic-export-contract-v1.md),
2026-09-22). Transaction shape pre-declared by
[snapshot v1 spec §12.5](2026-08-25-run-snapshot-v1.md); data boundaries fixed
by [ADR-0036](../adr/0036-invited-trial-data-and-role-boundary.md); action
allowlist authority [ADR-0038](../adr/0038-run-snapshot-contract-and-loopback-security.md)
§5 and §8.

## 1. Scope

One export transaction turns the validated Snapshot v1 document of the
selected run into a shareable diagnostic pair: a versioned JSON contract and
a Markdown human view. It exists so an invited trial can produce evidence
(first-run completion, closed-loop integrity, comprehension source facts)
without hidden telemetry, an upload endpoint, or a second authority. The
export is a projection — it collects nothing that the snapshot does not
already project.

## 2. Identity and versioning

- `exportContract = {"id": "diagnostic-export.schema.v1", "version": 1}`.
- The export is a **long-lived backward-compat surface** (ADR-0038 §8):
  schema changes require a new version number; readers reject unknown
  versions fail-closed. Internal snapshot versions carry no such promise.
- The Markdown view is rendered from the same inputs as the JSON; the two
  are written as one atomic pair and neither exists without the other.
- The written pair states its own transaction bindings in-band in a
  `transaction` block (`participantReviewed`, `atomicJsonAndMarkdown`,
  `confinedToTrialExport` — all true by construction of the accepted
  transaction). `previewHash` is deliberately not in-band: it is the hash
  of these very bytes, so it is verifiable from the file itself and the
  file name (`export-<first 12 hex>`).

## 3. Content contract

Every projected fact is an **envelope**:
`{"availability": "known"|"unknown"|"stale"|"inconsistent", "reasonCode": string|null, "value": <domain value|null>}`.
`value` carries the snapshot's domain result only when the availability is
`known`; otherwise it is `null` and `reasonCode` names the snapshot's reason
code. The export never guesses, never strengthens, and never substitutes a
stale value for a current one. The candidate is a **pure function of the
validated snapshot and the request's `participantRef`** — no clock and no
transaction-time value lives inside the hashed bytes, so the preview→write
binding stays satisfiable on a live clock (the pair was written when the
filesystem says it was; the hash names what the participant reviewed).

| Field | Source (Snapshot v1) | Notes |
| --- | --- | --- |
| `exportContract` | constant | identity above |
| `participantRef` | request, optional | participant-supplied only; echoed verbatim; never generated or persisted by the product |
| `usage` | constant | `{"evidence": false, "acceptanceInput": false, "upload": "none-manual-share-only"}` |
| `run.runId` | `identity.run` envelope | |
| `run.label` | `identity.run` envelope | |
| `run.sourceSetHash` | `sources.sourceSetHash` | the hash the export was built from |
| `run.builtAt` / `run.buildState` | `identity.snapshot` | |
| `run.snapshotSchemaVersion` | `schemaVersion` | |
| `product` | `identity.product` envelope | name + package version |
| `profile` | `identity.profile` envelope | declared/effective tier, confirmedBy |
| `intent` | `intent.summary` envelope | comprehension fact 1 |
| `verdict` | `evaluation.verdict` envelope | comprehension fact 2 |
| `blockers` | blocking `evaluation.findings` + `limitations.items` | comprehension fact 3; findings carry `findingId`, `severity`, `disposition`, `issue`, `ownerKind` (the finding owner's kind — declaration/artifact/decision/unknown), `repair`; limitations carry `code`, `summary` |
| `nextAction` | `nextActions.primary` envelope | comprehension fact 4; carries `owner`, `kind`, `label`, and boolean `hasCopyableCommand` — **the command text itself is never exported** |
| `loop` | `execution.repair` envelope | `rounds`, `closeReason`, `waitingForHuman` |
| `progress` | `execution.progress` envelope | observed stages + latest |
| `counts` | `evaluation.criteria`, `evaluation.coverage` | criteria total, coverage declared/reviewed/unreviewed/complete |
| `transaction` | constant | the write's own bindings, stated in-band: `participantReviewed`, `atomicJsonAndMarkdown`, `confinedToTrialExport` (all true by construction; no hashes — the preview hash is verifiable from the bytes and the file name) |
| `notCollected` | constant | states that comprehension timing, participant answers, and intervention records are human-observed/human-recorded by the trial facilitator and never collected by the product |

**Exclusions (hard):** source code and source excerpts, secrets and
credentials, unselected artifacts, raw model reasoning, participant timing,
participant answers, generated participant identifiers, telemetry of any
kind. Free-text finding `issue`/`repair` fields are part of the audited
run's point-back record and are included; everything else on this list is
structurally absent.

## 4. Transaction contract

Both routes sit behind the session token, Origin validation, and the fixed
§11 protections of the snapshot spec. Payloads are closed schemas: unknown
field, missing field, wrong type, or wrong value fails with
`ACTION_PAYLOAD_INVALID`; non-JSON bodies fail with `MALFORMED_JSON`.

### 4.1 Preview — `POST /api/v1/actions/diagnostic-export/preview`

Request: `{"schemaVersion": 1, "action": "diagnostic-export-preview", "participantRef": string?}`.

Response: `{"schemaVersion": 1, "action": "diagnostic-export-preview", "previewHash": <digest>, "expectedSourceSetHash": <digest>, "json": <candidate>, "markdown": <string>}` (the `action` echo mirrors the refresh response's precedent).

- Builds the candidate from the session's currently served snapshot and the
  request's `participantRef`; writes nothing anywhere.
- `previewHash` = SHA-256 over the exact canonical JSON bytes of the
  candidate (fixed serialization: UTF-8, `ensure_ascii=False`, sorted keys,
  2-space indent), written as 64 lowercase hex characters. The snapshot-form
  digest fields (`expectedSourceSetHash`, `run.sourceSetHash`) keep the
  snapshot's `sha256:<hex>` form. Because the candidate is clock-free, a
  preview taken at time T is still writable at T+Δ — the S36 rejections fire
  only on real binding changes (a rebuilt snapshot with a different source
  set, or different reviewed bytes), never on elapsed time.
- A snapshot rebuild between preview and write is detected by the write's
  `expectedSourceSetHash` check (S36), not by caching.

### 4.2 Write — `POST /api/v1/actions/diagnostic-export/write`

Request: `{"schemaVersion": 1, "action": "diagnostic-export-write", "expectedSourceSetHash": <digest>, "previewHash": <digest>, "participantReviewed": true, "participantRef": string?}`.

- `participantReviewed` must be the literal `true`; the UI flow enforces an
  explicit review step before this request exists. Any other value, or a
  missing field, fails closed.
- `expectedSourceSetHash` must equal the source-set hash of the candidate
  that produced `previewHash`; a mismatch fails (S36) and writes nothing.
- The write re-derives the candidate from the current snapshot and re-checks
  the preview hash; only then does it stage and commit the pair.

Response: `{"schemaVersion": 1, "action": "diagnostic-export-write", "written": ["trial-export/<name>.json", "trial-export/<name>.md"], "snapshot": <rebuilt document>}`.
Run-root-relative paths only; absolute paths never appear.

### 4.3 Write boundary and atomicity

- Targets live only under `<run_root>/trial-export/`; file names are
  `export-<first 12 hex of previewHash>.json` / `.md`, so the name is derived
  from the exact bytes the participant reviewed. An existing target fails the
  write: the pair itself enters the next snapshot's source set (run-facts /
  run-status read the run tree), so a repeat export rebinds to a new hash and
  a new name — repeated exports are ordinary pairs, never overwrites. An
  existing name can only mean a partial pair from an interrupted transaction
  or a hash collision, and both fail closed. A transaction failure
  (`EXPORT_WRITE_FAILED`) is not blind-retryable: recovery is a fresh preview
  with rebound hashes.
- A dedicated containment primitive (owned beside the Evidence artifact
  containment module) resolves and confines the write targets; reserved
  names (`manifest.jsonl`) and any path outside the boundary fail closed.
- Commit is staged: both files are written to temporary names inside
  `trial-export/` and then renamed into place; if the second rename fails,
  the first is rolled back so no partial pair survives (S36).
- On success the session performs one full snapshot rebuild (§12.5). A
  rebuild failure surfaces as `SNAPSHOT_BUILD_FAILED`; the committed pair
  remains (it was reviewed), and the response carries no snapshot document.
- `EXPORT_WRITE_FAILED` (500) covers any transaction failure after preview;
  the error envelope carries no generated export.

## 5. Markdown human view

The Markdown view renders the same facts for human review: a header block
(contract identity, snapshot built-at, `participantRef` line when present, and
the non-Evidence / non-acceptance / no-upload usage boundary), the four
comprehension facts with their availability labels, loop and progress facts,
counts, limitations, and the `notCollected` statement. Non-`known` facts
render their availability label and reason code, never a guessed value. The
view names the trial protocol document
(`docs/agents/run-console-read-only-trial.md`) as the disclosure companion
for facilitator-recorded interventions.

## 6. Test plan (binding)

| ID | Scenario | Required outcome |
| --- | --- | --- |
| S35 | Contract accepted and enabled | preview/write routes are live; the prior 409 gate, snapshot limitation, and disabled UI control are gone; role-attestation stays gated |
| S36 | Source set or candidate changes between preview and write | write rejected; no JSON/Markdown pair exists, including after an injected mid-commit failure (rollback proven) |
| S37 | Write succeeds | exactly one JSON/Markdown pair under `trial-export/`, named from the preview hash; `evidence/`, Manifest, verdict, and acceptance facts unchanged; full rebuild follows; export fields match the served snapshot envelopes exactly |

Additional binding checks: closed-payload rejection matrix for both routes;
containment (path escape, reserved name, non-`trial-export` target);
`notCollected` and exclusion scan (no timing/answers/interventions/source
text in any exported byte); participant-ref passthrough without persistence;
long-lived-reader version rejection.

## 7. Non-claims

- The export satisfies no gate and substitutes for no acceptance decision.
- A completed export is not trial evidence by itself; it is the instrument a
  separately authorized trial uses to produce evidence.
- `G-RO-TRIAL-PASS` remains NOT SATISFIED until real external evidence
  arrives, and role attestation stays disabled.
