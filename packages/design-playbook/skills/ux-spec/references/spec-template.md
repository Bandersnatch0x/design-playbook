<!-- spec-schema: 2 -->

# [Feature Name] Interaction Design Spec

schema 2 adds the L2-L5 structured field blocks (per-page duty table, path table, per-page five-state matrix) consumed by the deepened G1 gate. Legacy schema-1 specs are not re-checked; new runs author against this template.

## L1 Positioning and intent
- User-visible goal:
- Target user:
- Scene list:
- Non-goals:
- Behavior boundary: always / ask first / never

(Shaping-session projection obligation: each of the five fields maps one-to-one to `l1.goal / l1.target_user / l1.scenes / l1.non_goals / l1.boundaries`; assumption values are explicitly annotated "Assumption" and point to the contract field path.)

## L2 Information architecture
- Spatial region definitions:
- Region boundary rules:
- Content growth rules:

### Page duties

| Page | Duty |
| --- | --- |
| <page-id> | <one owner duty per page — what this page alone is for> |

## L3 Core flow
- State list:
- Primary path:
- Branch paths:

### Paths

| Path | Steps |
| --- | --- |
| P1 | <page/decision points in order — primary path; structural alternatives go through CP-B> |

## L4 Component behavior detail
- Component role and function list
- Default / hover / loading / disabled / error states
- L4 declares control behavior only; reuse / no-internal-change constraints must name exceptions (for example, allow a minimal patch when they conflict with L5).

## L5 Edge conditions
- Empty state:
- Loading state:
- Error state:
- Permission downgrade:

### Five-state matrix

| Page | initial | loading | success | failure | empty |
| --- | --- | --- | --- | --- | --- |
| <page-id> | <value or n/a (reason)> | <value> | <value> | <value> | <value> |

## L6 Acceptance criteria
- Each acceptance criterion is a top-level list item, explicitly containing `Given` → `When` → `Then` in order (fixed order), with its required evidence stated, and citing a reachable path from the L3 path table as `(path: P<n>)`
  - Required evidence: declaration coverage / target-viewport render / interaction record or automated check / applicable test, type, lint, build
  - When evidence is a runtime state, name the capture seed (state to capture + capture type, e.g. "error-state screenshot"); do not write selector/URL/actions
- Design done definition:

---

## Worked snippet (illustrative)

For an agent-ops list: a failed item must show cause + retry (L3/L4); no-data shows a non-blank empty state (L5); without permission the dangerous action is disabled with a reason (L5); acceptance ticks each of these (L6) and names the path that exercises it. Adapt to the actual product; this is not a fixed domain.
