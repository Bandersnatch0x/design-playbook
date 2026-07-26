# Craft detectors decision map

**Status:** Closed
**Opened:** 2026-07-26
**Source:** post-v0.6 product-next frontier selection + one-question-at-a-time grill

## Problem

`craft-guard` names broad anti-slop targets, but an agent can claim completion without showing that each target was inspected against rendered UI and source. `ui-evaluator` can point findings back to `craft`, yet it has no stable craft-stage audit input distinguishing `clear`, `hit`, and missing proof.

## Locked decisions

1. First increment ships **8 cross-product detectors**: primary hierarchy, repeated card wall, nested/floating containers, one-note palette, shape/pill overuse, type-scale mismatch, text-as-control/icon misuse, and decorative/purposeless motion.
2. Detectors are a **skill protocol**, not a Python scanner, browser analyzer, or new runtime.
3. Default input is **rendered UI + source**. Missing input is an explicit evidence gap, never a silent full check.
4. Detector authority is **advisory**. `ui-evaluator` remains the sole owner of declaration mapping, severity, and verdict. No new `validate_run.py` craft gate.
5. Every detector defines observable signals, rendered evidence, source evidence, legitimate exceptions, and a positive fix.
6. A verified project baseline wins over generic anti-slop taste unless safety, usability, or an explicit declaration says otherwise.
7. Output is `.scratch/<run>/craft-guard.md`, containing one ledger row per detector with `clear|hit|blocked`. A hit includes evidence and a positive fix; detector output does not assign severity or verdict.
8. `blocked` continues into evaluation as a craft proof gap. Implemented UI cannot claim full craft Pass from missing proof; planning-only work may record the detector as `N/A` with reason.
9. Findings recirculate through the existing owner map. Detectors do not directly own edits.
10. Verification uses two agreed seams: a deterministic static publication gate for catalog/fixture contract, and a real skill dogfood from rendered+source input through ledger to evaluator findings.
11. Three authored contrast fixtures cover SaaS dashboard, landing/product, and existing-brand UI. Every detector has a `hit` and `clear`; baseline exception behavior is explicit.

## Detector set

| ID | Detector | Primary concern |
| --- | --- | --- |
| CRAFT-01 | Primary hierarchy | Competing or absent primary action/region |
| CRAFT-02 | Repeated card wall | Undifferentiated repeated cards replacing useful structure |
| CRAFT-03 | Nested/floating containers | Cards inside cards or section-as-floating-card composition |
| CRAFT-04 | One-note palette | UI dominated by one hue family without semantic contrast |
| CRAFT-05 | Shape/pill overuse | Excess rounded containers or text pills where standard controls fit |
| CRAFT-06 | Type-scale mismatch | Display-scale text in compact surfaces or hierarchy encoded by size alone |
| CRAFT-07 | Text-as-control/icon misuse | Text buttons where familiar icons/controls communicate action better |
| CRAFT-08 | Decorative/purposeless motion | Motion that explains no state change or destabilizes interaction |

## Testing seams

- **Static publication seam:** repository validation fails when detector IDs, required fields, ledger statuses, fixture coverage, or exception coverage drift.
- **Skill dogfood seam:** given rendered and source evidence, `craft-guard` emits all eight ledger rows; `ui-evaluator` consumes hits and blocked rows through existing point-back semantics.

## Non-goals

- Automatic computer-vision scoring or DOM heuristics.
- A numeric craft score.
- New G7 or changes to G1-G6 authority.
- Copying third-party detector prose or implementation.
- Treating generic taste as stronger than a verified project baseline.
- DTCG tokens, Storybook/Ladle capture, or a new evidence provider.

## Completion

Tickets 01-04 resolved. Implementation commits: `e86c4b5`, `7f43acb`, `06c9e5d`, `0d40450`. Ubuntu CI runs `30208980787`, `30209240916`, `30209670547`, and `30210795805` green. Final documentation HEAD verified separately after closure commit.
