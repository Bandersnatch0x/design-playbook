# ADR-0041: v10 workbench delta — reviewer-record criteria, no machine verdicts at G5

Accepted (grilling session, 2026-08-28). Extends the Stage 6 workbench
(#36, v9 spec) toward the Stitch v10 design without weakening the
capture-vs-judge boundary.

## Context

The Stitch v10 export (preview-confirm-v10) adds a SPEC MATRIX left
pane, a header criteria counter, a dark toggle, a sign-off CTA, and two
annotation tools (box, ruler) over the landed v9 workbench. The mock
displays machine gate verdicts ("G1 通过", "待整改", a G1-G8 chip row) —
but at G5 time the machine gates have not run, so showing them would
fabricate evidence.

## Decision

1. The SPEC MATRIX pane lists L6 acceptance criteria parsed from the
   run's spec.md by the owner parser `scripts/g1_spec.py`
   (ADR-0039: no second L6 parser). Missing/unparseable spec renders a
   visible empty state, never fake rows, never a hard error.
2. Checkboxes are the human reviewer's verification record ONLY. They
   are persisted additively as `criteria_review` in
   confirm-round-N.json. No machine gate states, no G1-G8 chips at G5;
   the design mock's verdict badges are explicitly rejected.
3. The header widget counts reviewer ticks (N/M), hidden when no
   criteria exist.
4. The primary confirm CTA is relabeled 确认签署决策 / "Confirm & sign
   decision"; CONFIRM_LABELS keeps the old labels in the union so
   historical records and the recognizer stay valid (ADR-0008 floor
   unchanged).
5. Box annotations extend the anchors payload additively; the ruler is
   a transient probe with no persistence.

## Consequences

- confirm-round consumers must treat `criteria_review` as optional.
- Any future wish to show machine gate states in the workbench requires
  a live validate_run evaluation seam and supersedes this ADR.
