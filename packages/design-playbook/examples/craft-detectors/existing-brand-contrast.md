# Existing-brand baseline contrast

Worked fixture for registry audit rows against a verified project baseline. Registry entries are evaluated in seven-column form; generic registry outcomes never override a verified baseline, and safety or explicit declarations override baseline consistency.

## Verified baseline exception

- Detector: CRAFT-05
- Generic signal: product uses pill geometry across navigation and compact actions.
- Rendered evidence: pill silhouette is consistent, sparse, readable, and does not obscure control state.
- Source evidence: confirmed project radius token and shared primitives apply the geometry consistently.
- Verified baseline: project `DESIGN.md` explicitly names capsule geometry as a first-party brand convention; binding status is `ready`.
- Baseline disposition: clear
- Reason: verified project choice wins generic detector taste.

## Override boundary

- Detector: CRAFT-07
- Generic signal: dangerous account deletion is represented by an unlabeled trash icon.
- Rendered evidence: destructive action has no text, consequence, or confirmation cue.
- Source evidence: IconButton invokes deletion directly without confirmation Dialog.
- Verified baseline: project uses icon-only toolbars.
- Override disposition: hit
- Reason: safety, usability, and explicit dangerous-action declarations override baseline consistency.
- Positive fix: retain baseline icon treatment for ordinary tools, but use explicit destructive text and confirmation for account deletion.

## Craft audit

| ID@ver | Applicability | Predicate reason / missing proof | Result | Rendered evidence | Source evidence | Exception check | Positive fix |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CRAFT-05@1 | applicable | - | clear | Pill silhouette is consistent, sparse, and does not obscure control state | Confirmed project radius token and shared primitives apply the geometry consistently | Verified baseline: capsule geometry is a first-party brand convention; binding status is `ready` | - |
| CRAFT-07@1 | applicable | - | hit | Destructive action has no text, consequence, or confirmation cue | IconButton invokes deletion directly without confirmation Dialog | safety, usability, and explicit dangerous-action declarations override baseline consistency | Retain baseline icon treatment for ordinary tools, but use explicit destructive text and confirmation for account deletion |
| CRAFT-08@1 | not-applicable | Audited brand surfaces declare no motion; static brand audit has no motion face in scope | - | - | - | No motion face to check | - |
| CRAFT-06@1 | blocked | Dense-container type token map was not included in the brand audit input | - | Rendered heading observed at brand display scale | Type token map absent from review input | No exception can be checked without source | Include the type token map in review input before complete craft Pass |
