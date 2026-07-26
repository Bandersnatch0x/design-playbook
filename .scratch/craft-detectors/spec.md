# Craft detector protocol

**Status:** ready-for-agent

## Problem Statement

People using Design I/O can receive a generic statement that craft checks passed without knowing whether common AI-generated visual failures were inspected on the rendered surface and in source. Existing `craft-guard` guidance names broad anti-slop targets, while `ui-evaluator` owns declaration-backed findings and verdicts. Missing middle layer is an auditable craft-stage protocol: exhaustive enough to prevent skipped checks, evidence-rich enough to support point-back findings, and subordinate to verified project visual language.

## Solution

Add an authored eight-detector protocol to `craft-guard`. Each detector examines rendered UI and source, records observable evidence, checks legitimate exceptions, and proposes a positive fix. Each run writes `.scratch/<run>/craft-guard.md` with one `clear`, `hit`, or `blocked` row per detector. `ui-evaluator` consumes this ledger as supporting craft input, maps real problems to owning declarations, and retains sole authority over severity and verdict.

Ship three contrast fixtures and a deterministic static publication gate. Fixtures prove every detector can distinguish a hit from a clear case and that a verified existing-brand baseline can override generic taste. A real dogfood run proves the skill protocol produces the ledger and evaluator recirculation behavior without a detector runtime.

## User Stories

1. As a UI builder, I want a fixed detector set, so that craft review does not skip inconvenient visual checks.
2. As a UI builder, I want each detector to name observable signals, so that review is more specific than “looks generic.”
3. As a UI builder, I want rendered evidence, so that findings reflect user-visible composition.
4. As a UI builder, I want source evidence, so that fixes target real structure and controls rather than screenshot guesses.
5. As a UI builder, I want missing rendered or source input recorded, so that incomplete inspection cannot masquerade as a full pass.
6. As a product owner, I want one explicit primary-hierarchy check, so that competing calls to action are surfaced.
7. As an operator, I want repeated card-wall layouts challenged, so that dense workflows remain scannable.
8. As a user, I want nested and floating containers challenged, so that page sections do not become decorative cards inside cards.
9. As a user, I want one-note palettes challenged, so that semantic state and hierarchy remain legible.
10. As a user, I want excessive pills and rounded shapes challenged, so that controls use familiar forms.
11. As a user, I want type scale checked against context, so that compact work surfaces do not read like landing-page heroes.
12. As a user, I want text-as-control and icon misuse checked, so that familiar actions use recognizable controls.
13. As a motion-sensitive user, I want decorative motion challenged, so that movement explains state and respects interaction.
14. As a maintainer, I want detector output advisory, so that generic taste cannot silently become a machine gate.
15. As an evaluator, I want detector output free of severity and verdict, so that declaration mapping remains my responsibility.
16. As an evaluator, I want a stable ledger path, so that craft-stage output is discoverable without parsing chat.
17. As an evaluator, I want exactly one row per detector, so that `clear` differs from not checked.
18. As an evaluator, I want `blocked` rows carried forward, so that missing proof remains visible.
19. As an evaluator, I want implemented UI with craft proof gaps prevented from a full craft Pass, so that verdict claims match evidence.
20. As a planning-only user, I want explicit `N/A` handling, so that absent rendering is honest rather than falsely blocking implementation work.
21. As an existing-product maintainer, I want a verified baseline to override generic taste, so that intentional brand language is preserved.
22. As a safety owner, I want safety, usability, and explicit declarations to override baseline exceptions, so that consistency cannot excuse harmful UI.
23. As a declaration owner, I want detector hits mapped through the existing recirculate map, so that fixes begin at the correct layer.
24. As a maintainer, I want positive fixes, so that findings describe a useful target instead of accumulating bans.
25. As a maintainer, I want three contrasting product scenes, so that detectors are not tuned only to dashboards.
26. As a maintainer, I want every detector represented by hit and clear fixtures, so that both sensitivity and restraint are reviewed.
27. As a maintainer, I want a baseline-exception fixture, so that generic anti-slop rules cannot erase intentional visual systems.
28. As a release owner, I want deterministic validation of detector IDs, fields, statuses, and fixture coverage, so that protocol drift fails CI.
29. As a release owner, I want real dogfood, so that prose shape alone is not mistaken for agent executability.
30. As an integrator, I want no new runtime dependency, so that plugin installation remains lightweight.
31. As a contract owner, I want G1-G6 unchanged, so that craft advice does not alter run authority.
32. As an auditor, I want craft ledger distinguished from G6 evidence, so that a detector judgment is never mistaken for a captured runtime artifact.

## Implementation Decisions

- Detector catalog has eight stable IDs covering hierarchy, repeated card walls, nested/floating containers, one-note palettes, shape/pill overuse, type-scale mismatch, text-as-control/icon misuse, and decorative/purposeless motion.
- Detector catalog is authored, self-contained skill reference material. No third-party prose or implementation is copied.
- Each detector specifies purpose, rendered signals, source signals, legitimate exceptions, owner-mapping hints, and positive repair targets.
- Default execution requires rendered UI plus relevant source. A detector may use available evidence but records `blocked` when required proof is unavailable.
- Ledger is run-local craft output at `craft-guard.md`; it is not a manifest entry and not L6 evidence.
- Ledger has exactly one row per detector with `clear`, `hit`, or `blocked`, plus concise evidence. Hit rows include positive fix. Blocked rows name missing proof.
- Planning-only work may record an explicit `N/A` rationale outside implemented-UI craft completion; it cannot claim rendered inspection.
- Detector results are advisory. They never assign severity, verdict, or machine-gate status.
- Evaluator consumes ledger as supporting craft input, checks declarations and verified baseline, maps owner, then emits standard point-back findings when warranted.
- Verified project baseline wins over generic detector taste. Safety, usability, and explicit declarations still take precedence.
- Existing recirculate map remains authority for repair ownership.
- No new run gate, detector runtime, browser analyzer, static source scanner, numeric score, or provider contract is introduced.

## Testing Decisions

- Tests observe two agreed public seams: repository publication validation and an end-to-end skill dogfood artifact flow.
- Static validation checks external contract, not parser internals: stable detector IDs, required detector sections, allowed ledger statuses, three contrast fixture scenes, hit/clear coverage for all IDs, and baseline exception coverage.
- Negative tests mutate a fixture or required detector field and require a named hard failure, preventing silent drift.
- Contrast fixtures are authored worked examples, not snapshots generated by the validator.
- SaaS dashboard fixture exercises operational density and card/container hierarchy.
- Landing/product fixture exercises type scale, palette, primary hierarchy, and decorative motion.
- Existing-brand fixture exercises baseline precedence and legitimate shape/palette exceptions.
- Real dogfood starts from rendered and source inputs, produces all eight ledger rows, and passes results to evaluator output. At least one hit, one clear, and one blocked/degraded evidence path are observed across dogfood scenarios.
- Existing static validator and run-seam suites remain green. No tests assert private helper structure.

## Out of Scope

- Computer vision, screenshot scoring, browser DOM instrumentation, or automated CSS linting.
- Numeric craft quality scores.
- New MCP tools or dependencies.
- Changes to G1-G6, Preview confirmation authority, or Evidence manifest authority.
- Automatic repair without declaration owner mapping.
- Third-party detector text redistribution.
- DTCG token schemas, Playwright CLI provider work, Storybook/Ladle capture, or manifest schema work.

## Further Notes

Deletion test: detector protocol earns its module boundary because catalog complexity, exceptions, evidence requirements, and output contract can evolve behind one required reference. Removing it returns craft completion to broad un-audited prose. Ledger remains supporting declaration audit, not runtime evidence or verdict authority.
