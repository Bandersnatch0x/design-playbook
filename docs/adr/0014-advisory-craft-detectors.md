# ADR-0014: Advisory craft detector protocol

## Status

Accepted and implemented (2026-07-27).

## Context

`craft-guard` declared anti-slop, hierarchy, motion, and feedback quality, but completion did not prove each common failure mode was inspected against rendered UI and source. `ui-evaluator` already owns declaration-backed findings, severity, and verdict. G1-G6 validate run artifact authority and shape; none should become a generic taste gate.

A static source scanner cannot reliably judge visual composition. A browser analyzer or computer-vision score would add runtime and calibration cost before stable rules exist. Pure prose without an audit record lets agents silently skip checks.

## Decision

`craft-guard` owns an authored protocol of eight stable detectors: primary hierarchy, repeated card walls, nested/floating containers, one-note palettes, shape/pill overuse, type-scale mismatch, text-as-control/icon misuse, and decorative/purposeless motion.

For implemented UI, each detector inspects rendered UI plus relevant source and records exactly one `clear`, `hit`, or `blocked` row in `.scratch/<run>/craft-guard.md`. Each row includes rendered evidence, source evidence, exception check, and positive fix when hit. Missing required proof is `blocked`, never silent success.

Detector output is advisory. It does not assign declaration source, severity, or verdict. `ui-evaluator` verifies detector evidence, applies verified project baseline and explicit declarations, maps the owning declaration through its existing recirculate map, and retains verdict authority.

A verified project baseline wins over generic anti-slop taste. Safety, usability, and explicit declarations still override baseline consistency.

Craft ledger is a craft-stage audit record. It never enters `evidence/manifest.jsonl`, never becomes an L6 evidence row, and does not add G7 or change G1-G6.

Protocol publication is deterministically validated through stable IDs, required fields, allowed statuses, and authored contrast fixtures. Real dogfood verifies skill execution and evaluator consumption.

## Consequences

- Craft completion distinguishes clear checks from skipped checks.
- Findings have observable evidence and positive repair targets.
- Existing-product visual language is preserved instead of normalized to generic taste.
- `ui-evaluator` remains sole semantic and verdict authority.
- Static validation checks protocol integrity, not aesthetics.
- First version adds no runtime dependency, numeric score, computer vision, or DOM heuristic engine.
