# Existing-brand baseline contrast

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
