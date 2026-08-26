# ADR-0039: One owner per authority read seam

Accepted (architecture review, 2026-08-26). Extends ADR-0025 (finding
syntax facts), ADR-0026 (containment reads under arbitrary roots), and
ADR-0017 (bind-snapshot read) without moving write ownership.

## Context

The 2026-08-26 review found five duplicated read seams, not new product
behaviour. Each had more than one consumer already, and each duplicate
could disagree on a torn write, an overlap invariant, a finding field
line, an artifact's presence, a preview round filename, or a path
escape. The healthy boundaries (snapshot projection, evidence write
timing, `_diagnostics.Finding`) were not in question.

## Decision

1. Point-back finding-paragraph grammar lives in `finding_syntax`. G2-G4
   keep policy. This is the third syntax-facts module beside ledger and
   Verdict (ADR-0025).
2. `contract_v1` owns reading `contract-bind.json` and the disjoint
   open/assumed/stale invariant. G7, G12, and the Run Snapshot project
   that one result into their own vocabularies.
3. `RunFacts.artifact_state` reports `complete | missing | unreadable`
   for every stated run artifact. Consumers do not re-stat files.
4. Preview round filenames (`confirm-round-N.json`,
   `decision-round-N.json`, `round-N.html`) are constructed by
   `preview.integrity`. Lock filenames stay local to the writer.
5. `containment.read_under(root, relpath)` is the generalized read
   primitive. Evidence `write_target` / `read_artifact` remain the
   ADR-0026 operations (run-root-relative paths, evidence/ boundary,
   distinct existence timing) as specializations of the same resolver.
   Run Console source reads consume `read_under` instead of mirroring
   escape classes.

## Considered options

- Keep per-consumer parsers: rejected because a torn or overlapping bind
  snapshot could pass G7 and fail the Console.
- Collapse evidence write and read into one mode flag: already rejected
  by ADR-0026; this ADR does not reopen that.
- Move containment out of the Evidence package: rejected; the
  generalization is an extra operation, not a new owner.

## Consequences

- Bind overlap is a G7 finding, not a silent G7 Pass.
- Finding-field and severity-axis fixes land in one module.
- Escape-class tests for source reads are written once.
- ADR-0026's TOCTOU limit still applies: resolution does not write.
