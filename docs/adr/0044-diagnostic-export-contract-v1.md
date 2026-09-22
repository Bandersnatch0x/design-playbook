# ADR-0044: Diagnostic export contract v1 is accepted

## Status

Accepted (roundtable verdict A with user preauthorization 「全部按推荐」,
2026-09-22).

Unlocks the export transaction defined by
[ADR-0036](0036-invited-trial-data-and-role-boundary.md) §2 and
[snapshot v1 spec](../specs/2026-08-25-run-snapshot-v1.md) §12.5; it does not
satisfy `G-RO-TRIAL-PASS` and does not unlock any other typed action.

## Context

The invited-trial protocol promises each participant an explicitly initiated,
reviewed Diagnostic export before anything is shared, and the roadmap accepts
no evaluation of the 90-day horizon "against exported evidence" without one.
The 2026-08-25 snapshot specs left the export gate open ("separately accepted
Diagnostic export owner"), and RCV1-011 resolved `disabled-by-gate` on
2026-08-27 with a re-derivation path reserved. Six independent product audits
(2026-09-21) converged on the same structural deficit: external evidence ≈ 0,
and the single minimum prerequisite for every acceptance-floor metric is the
export contract. The unlock condition was already fixed by authority —
snapshot v1 §12.5 binds the action's enablement to "the separate Diagnostic
export schema is accepted", not to the trial gate.

## Decision

1. **Contract v1 is accepted.** Export identity:
   `exportContract = {"id": "diagnostic-export.schema.v1", "version": 1}`.
   One export transaction writes exactly one JSON document and one Markdown
   human view derived deterministically from the same inputs.
2. **Two phases, preview first.** Preview validates the closed request and
   returns the exact candidate JSON, the exact Markdown, and a `previewHash`
   over the canonical JSON bytes; it writes nothing. Write requires the same
   `expectedSourceSetHash` and `previewHash`, an explicit
   `participantReviewed` acknowledgement, and writes the pair atomically —
   both files or neither — then performs a full snapshot rebuild. The owner
   transaction is the Run Console's export transaction: the source registry
   maps it under the authority key `diagnostic-export` with registry kind
   `export-transaction`, and the written pair states its own transaction
   bindings in-band (participant-reviewed, atomic, `trial-export/`-confined)
   so a persisted record can be audited without re-running anything.
3. **Export content is snapshot-derived only.** The payload projects the
   validated Snapshot v1 document: run identity, source-set hash, intent,
   verdict with its availability label and reason, blocking findings and
   limitation codes, next owner and action kind, run profile, and the
   criterion/evidence counts. It contains no source excerpts, no raw model
   reasoning, no secrets or credentials, no unselected artifacts, and no
   participant timing or answers — comprehension timing and answers are
   human-observed and human-recorded by the trial facilitator, and the export
   says so explicitly in a `notCollected` block.
4. **Participant identifier is participant-supplied or absent.** An optional
   `participantRef` may be supplied by the participant, is shown in the
   preview, and is never generated, inferred, or persisted by the product
   (ADR-0036 §8).
5. **Write boundary.** Files are written only under the selected run's
   `trial-export/` subtree, with names derived from the reviewed
   `previewHash`, through a containment primitive owned beside the Evidence
   artifact containment module. The export never writes under `evidence/`,
   never updates a Manifest, never changes a verdict, never uploads, and
   never counts as acceptance. Both files carry non-Evidence / non-acceptance
   markers in-band (`usage` fields) and in the Markdown header.
6. **Repeated exports are ordinary.** Each export is a separate reviewed
   transaction; a repeated export never counts as a Voluntary repeat
   (roadmap trial boundary).
7. **Nothing else unlocks.** Role attestation (S31–S34) and every other
   typed action remain locked. This decision opens exactly the export
   preview/write pair, per §12.5's own unlock condition.
8. **The gate is unaffected.** `G-RO-TRIAL-PASS` is satisfied only by
   authorized real trial evidence; the export is the instrument that lets a
   trial produce evidence, never evidence itself.

## Consequences

- The snapshot limitation `diagnostic-export-contract-unavailable`, the two
  gated routes' `ACTION_UNAVAILABLE` response, and the disabled UI control are
  replaced by the enabled transaction; the RCV1-011 decision-record test is
  re-derived for the accepted state.
- Snapshot v1 spec S35–S37 become binding implementation tests; the parity
  spec's open-gate note records this gate as satisfied.
- Export evaluation remains possible only where runs exist; the export
  measures nothing that is not already projected, so no new collection
  surface is created.
- If S35–S37 cannot be satisfied without moving an authority boundary, the
  fallback (roundtable flip condition ②) is an owner-side CLI export with the
  Console staying disabled, and this ADR narrows to contract acceptance only.
- A 30-day dissent clause (roundtable record, scope-discipline seat) applies:
  if no new participant enters the comprehension check within 30 days of this
  acceptance, the Day-90 stop review is triggered early rather than awaited.
