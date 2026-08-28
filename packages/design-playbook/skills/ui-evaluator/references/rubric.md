# evaluator rubric

## How to choose dimensions

- **Landing page**: design quality / originality / craft / function
- **Console**: design quality / usability / information density / craft / consistency

Dimensions are read from the scene; no hardcoded list. **Every criterion must point back to a declaration.**

## Recirculate examples

| Finding | Surface wording | Points back to |
| --- | --- | --- |
| No retry on failure | Incomplete interaction | `spec` state flow |
| High-risk grey label | Color not prominent | `domain` + `components` |
| Button hardcodes hex (e.g. `#4f46e5`) | Code violates conventions | `design` token |
| List degrades to card wall | Wrong layout | `template` |

## Prohibited

- "Could be improved overall" with no specific pointer — not valid
- Changing CSS only without pointing back to the declaration
- Overwriting underspecified L5 with new aesthetic terminology

## preview seam health (supporting, ADR-0008)

If this run produced `preview*` artifacts (`.scratch/<run>/preview/log.md` + `confirm-round-*.json` exist), list it as a supporting finding:

- Read `preview/log.md` + confirm json: did feedback drive a revision, or did empty / unannotated anchors slide past the structural floor? `decision-round-*.json` is for audit / recovery only — it is not a confirmation authority or a second semantic input (ADR-0013).
- The structural floor (adapter, G5) only blocks empty feedback / unannotated anchors; **semantic** problems — e.g. example (zh): 「安师大」, a valid CJK string unrelated to the annotated element — cannot be blocked by the structural floor; catch them here.
- `source` is `preview* seam` (the orchestrator's preview-step contract), not UI source — use this when the defect is in the adapter loop contract rather than the generated UI itself.
- Process gaps (seam contract) are recorded separately from product findings (UI); do not mix them into the recirculate closure trail.

## observe* mirror surface (supporting)

If any capture in `evidence/manifest.jsonl` declares **`surface: mirror`** (or an equivalent note), there must be a finding:

```text
issue:    observe used semantic mirror, not live Fill host
source:   observe* seam
fix:      re-capture on live host URL when available; keep surface: mirror until then
severity: S1
```

Do not treat G6 artifact presence alone as proof the Fill tree was runtime-verified.
