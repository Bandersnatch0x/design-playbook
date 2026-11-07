<!-- Rule-registry part, located by ../rules.md -->

## CRAFT-01 — Primary hierarchy

```yaml
id: CRAFT-01
version: 1
title: Primary hierarchy
statement: Each viewport presents exactly one primary action or region that leads the scan (observable); competing primaries or no primary leave the target user unable to locate the main action at a glance (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface contains actions or regions that can claim primacy (contract detector subset does not disable this entry)
applicability-not-applicable: planning-only run, or a display surface with no action or region claiming primacy (observable reason required)
applicability-blocked: rendered or source evidence surface unavailable
check-type: protocol-check
check-inputs: rendered interface walkthrough; source primary variants and emphasis token usage
signals-rendered: more than one element claims primary emphasis, or no action or region leads the scan
signals-source: multiple primary variants, equivalent emphasis tokens, or page structure without a main landmark
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: deliberate equal-choice comparison supported by spec or a verified baseline (for example a side-by-side plan selection page)
false-positives: verified-baseline dual-primary layouts; a verified baseline outranks generic craft defaults and is recorded as an exception
owner: craft -> R4; template -> R4|R3
provenance: first-party
status: advisory
fix: preserve one scene-appropriate primary and make secondary actions recede through placement, density, or neutral treatment
related: CRAFT-06@1
history: 1 | 2026-08-14 | docs | initial registry registration, migrated from the craft-guard detector protocol six-field block
```

## CRAFT-02 — Repeated card wall

```yaml
id: CRAFT-02
version: 1
title: Repeated card wall
statement: List and collection surfaces present a scanning hierarchy that matches the comparison task (observable); undifferentiated card walls hide comparison columns and task grouping (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface contains a list or collection display
applicability-not-applicable: run has no list or collection display surface (observable reason required)
applicability-blocked: rendered or source evidence surface unavailable
check-type: protocol-check
check-inputs: rendered interface walkthrough; source card wrapper usage on records and regions
signals-rendered: most content appears as equal floating cards with no scanning hierarchy or task grouping
signals-source: repeated card wrappers applied to unrelated regions or to list and table records without a card-specific interaction
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: browsable collections where each item is a genuinely independent object and the verified baseline uses cards
false-positives: none recorded yet
owner: template -> R4; craft -> R4
provenance: first-party
status: advisory
fix: use list, table, band, or unframed grouping that matches comparison and action needs; reserve cards for independent items
related: CRAFT-03@1
history: 1 | 2026-08-14 | docs | initial registry registration, migrated from the craft-guard detector protocol six-field block
```

## CRAFT-03 — Nested or floating containers

```yaml
id: CRAFT-03
version: 1
title: Nested or floating containers
statement: Container framing follows interaction semantics rather than decoration (observable); nested borders and detached panels obscure which surface owns the content (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface combines sections or containers
applicability-not-applicable: run has a single flat region with no container composition (observable reason required)
applicability-blocked: rendered or source evidence surface unavailable
check-type: protocol-check
check-inputs: rendered interface walkthrough; source nesting of card primitives and section wrappers
signals-rendered: multiple nested borders, radii, shadows, or detached section surfaces obscure ownership
signals-source: card components nested for spacing, or full-width sections wrapped in decorative card primitives
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: a real framed tool, modal, or repeated item nested within an unframed page region
false-positives: none recorded yet
owner: template -> R4; components -> R4
provenance: first-party
status: advisory
fix: flatten page regions, group with spacing and dividers, and retain a frame only where interaction semantics require one
related: CRAFT-02@1
history: 1 | 2026-08-14 | docs | initial registry registration, migrated from the craft-guard detector protocol six-field block
```

## CRAFT-04 — One-note palette

```yaml
id: CRAFT-04
version: 1
title: One-note palette
statement: Unrelated semantic roles use distinguishable color roles (observable); one hue family carrying surfaces, accents, and states erases semantic contrast and hierarchy (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface carries multiple semantic roles
applicability-not-applicable: run has a single-semantic display surface with no state or role variation (observable reason required)
applicability-blocked: rendered or source evidence surface unavailable
check-type: protocol-check
check-inputs: rendered interface walkthrough; source color ramp and semantic token assignment
signals-rendered: backgrounds, surfaces, accents, and states rely on variations of one hue family
signals-source: one color ramp fills unrelated semantic roles, or repeated gradients replace neutral surfaces
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: verified monochrome brand systems with sufficient state, contrast, and hierarchy differentiation
false-positives: none recorded yet
owner: design -> R3; craft -> R4
provenance: first-party
status: advisory
fix: keep brand color selective, restore neutral surfaces, and use semantic colors only for named roles
related:
history: 1 | 2026-08-14 | docs | initial registry registration, migrated from the craft-guard detector protocol six-field block
```

## CRAFT-05 — Shape and pill overuse

```yaml
id: CRAFT-05
version: 1
title: Shape and pill overuse
statement: Control and tag geometry is specific to the control identity (observable); uniform pill geometry across unrelated controls erodes recognition (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface contains control or tag geometry variation
applicability-not-applicable: run has no control or tag geometry surface in scope, or one restrained standard radius declared for all controls (observable reason required)
applicability-blocked: rendered or source evidence surface unavailable
check-type: protocol-check
check-inputs: rendered interface walkthrough; source radius tokens and text-control primitives
signals-rendered: most labels, actions, and containers share pill geometry or oversized rounding
signals-source: large border-radius tokens applied globally, or text-in-rounded-rectangle controls replacing icons, toggles, tabs, or badges
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S1 / judgment
exceptions: verified brand geometry, or semantic chips and tags whose shape communicates grouping or status
false-positives: none recorded yet
owner: components -> R4; design -> R4
provenance: first-party
status: advisory
fix: use control-specific primitives and restrained radii; reserve pills for semantics that need compact grouping
related:
history: 1 | 2026-08-14 | docs | initial registry registration, migrated from the craft-guard detector protocol six-field block
```

## CRAFT-06 — Type-scale mismatch

```yaml
id: CRAFT-06
version: 1
title: Type-scale mismatch
statement: Type role matches container and workflow density (observable); hero-sized copy in compact panels crowds the content it labels (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface contains dense container typography
applicability-not-applicable: run has no dense container typography surface in scope (observable reason required)
applicability-blocked: rendered or source evidence surface unavailable
check-type: protocol-check
check-inputs: rendered interface walkthrough; source type token usage per container
signals-rendered: hero-sized copy dominates compact panels, or hierarchy depends on oversized text instead of structure
signals-source: display tokens used in cards, toolbars, dashboards, or narrow controls without a true hero context
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S1 / judgment
exceptions: literal landing-page hero, or a verified expressive product surface with stable responsive fit
false-positives: none recorded yet
owner: design -> R4; craft -> R4
provenance: first-party
status: advisory
fix: match type role to container and task density, using structure and weight before display scale
related: CRAFT-01@1
history: 1 | 2026-08-14 | docs | initial registry registration, migrated from the craft-guard detector protocol six-field block
```

## CRAFT-07 — Text-as-control and icon misuse

```yaml
id: CRAFT-07
version: 1
title: Text-as-control and icon misuse
statement: Frequent low-risk actions use the most recognizable control primitive (observable); verbose text pills where familiar symbols communicate better consume space and slow recognition (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface contains repeated high-frequency operations
applicability-not-applicable: run has no repeated operation surface in scope (observable reason required)
applicability-blocked: rendered or source evidence surface unavailable
check-type: protocol-check
check-inputs: rendered interface walkthrough; source control primitives for repeated actions
signals-rendered: repeated undo, close, save, formatting, color, or binary actions consume space as text buttons
signals-source: text buttons replace available icon buttons, swatches, segmented controls, toggles, or checkboxes
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: unfamiliar, high-risk, or ambiguous actions that require explicit text; accessibility names remain required for icons (a missing accessible name is a factual sub-signal the evaluator may rate independently on the severity axis)
false-positives: none recorded yet
owner: components -> R4; craft -> R4
provenance: first-party
status: advisory
fix: use familiar icon or control primitives with accessible names and tooltips where recognition needs support
related:
history: 1 | 2026-08-14 | docs | initial registry registration, migrated from the craft-guard detector protocol six-field block
```

## CRAFT-08 — Purposeful and reducible motion

```yaml
id: CRAFT-08
version: 2
title: Purposeful and reducible motion
statement: Every animation names the state change it explains, stays within the duration threshold, never carries information that is unavailable without motion, never blocks input, and is reduced under the reduced-motion preference as listed in the threshold (observable). Decorative, long, or unreducible motion distracts and can cause physical discomfort (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
threshold: motion-max <= 300ms; high-frequency-motion-max <= 150ms
applicability-applicable: run has Fill output and the surface contains motion
applicability-not-applicable: run has no motion on the audited surface (observable reason required)
applicability-blocked: motion source or interaction trace was not included in review input
check-type: protocol-check
check-inputs: rendered motion observation with and without the reduced-motion preference. Source motion implementation. Interaction trace when available. Threshold reading: feedback and transition motion <= 300 ms; motion on high-frequency interactions (hover, row focus, typing, list scrolling) <= 150 ms or none; under the reduced-motion preference remove looping and auto-playing motion, parallax, zoom and scale, large translations, depth changes, and blur transitions, and replace spatial transitions with an opacity cross-fade or a cut
signals-rendered: bounce, elastic, looping, or entrance motion with no state explanation. Durations above the threshold. Input ignored until an animation finishes. Reduced-motion capture still shows the removed motion classes. Meaning conveyed only by movement
signals-source: animation targets layout properties. No reduced-motion branch while animations exist. Durations or easings as raw literals instead of motion tokens
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: expressive game or immersive scene motion declared by product intent and kept clear of task controls. Motion that tracks a direct drag gesture
false-positives: micro-interaction transitions misread as decoration. Decide by whether a named state change is present
owner: craft -> R4; design -> R4
provenance: first-party
status: advisory
fix: remove decorative motion, bind each remaining animation to a named state change and a motion token within the threshold, keep input live during animation, and implement the reduced-motion substitutions.
related: PERF-01@2
history: 1 | 2026-08-14 | docs | initial registry registration, migrated from the craft-guard detector protocol six-field block; 2 | 2026-10-10 | docs | add duration threshold, high-frequency limit, reduced-motion substitutions, and non-blocking requirement (single source for craft-guard motion numbers)
```

## CRAFT-09 — Selector-specificity conflicts

```yaml
id: CRAFT-09
version: 2
title: Selector-specificity conflicts
statement: Style rules compose without fighting — no rule exists only to cancel or out-rank another, and adjacent blocks do not trade opposing spacing (observable); specificity duels and mutually cancelling padding or margin make every later edit unpredictable and leak visible seams to users (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: usability-heuristic
applicability-applicable: run has Fill output and styling source is available for the audited surface
applicability-not-applicable: planning-only run, or no styling source produced in the audited scope (observable reason required)
applicability-blocked: styling source unavailable for review — a rendered capture alone cannot prove selector intent
check-type: protocol-check
check-inputs: source selector stacks and override chains; spacing declarations between adjacent regions
signals-rendered: spacing or emphasis seams where adjacent blocks visibly disagree after overrides partially cancel
signals-source: a type-level and a class-level selector driving the same property in opposite directions; sibling blocks whose padding and margin cancel each other; override chains that exist only to defeat an earlier rule — a source-defect signal even when the rendered result happens to look right
evidence-layers: source>=1
evidence-method: static-inspection
severity-default: S2 / judgment
exceptions: a reset or normalization layer that neutralizes platform defaults once at the base of the cascade
false-positives: declared utility-class composition where high-frequency overrides are the intended model; judge the owning rule, not the override count
owner: template -> R4; craft -> R4
provenance: benchmark-input-only
status: advisory
fix: collapse each duel into one owning rule at one specificity level, and move spacing to the parent gap or to one side instead of opposing pairs
related: CRAFT-03@1
history: 1 | 2026-08-28 | docs | initial registry registration, benchmark-informed source-craft entry in first-party wording; 2 | 2026-10-10 | docs | authority recalibrated to usability-heuristic: a usability convention, neither taste nor a measured threshold
```

## CRAFT-10 — Structure encodes content

```yaml
id: CRAFT-10
version: 1
title: Structure encodes content
statement: Structural devices — numbered markers, eyebrow labels, dividers, tags — encode a true property of the content they decorate, and numbering appears only on real sequences (observable); structure that encodes nothing teaches users an order or grouping that does not exist (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface uses structural devices such as numbering, eyebrow labels, dividers, or tags
applicability-not-applicable: run has no structural device on the audited surface (observable reason required)
applicability-blocked: rendered or source evidence surface unavailable
check-type: protocol-check
check-inputs: rendered structural devices compared against the content's actual order and grouping; source markup semantics behind each device
signals-rendered: numbered markers on items with no meaningful order; eyebrow labels that repeat the heading or name no real category; dividers cutting through one continuous group; tags carrying no state or category
signals-source: ordered or step markup wrapping unordered content; decorative label elements bound to no content property
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: purely decorative devices declared by the bound baseline as identity elements and kept out of the reading order
false-positives: a sequence whose order is real but unfamiliar to the reviewer; verify the content's own order before flagging
owner: craft -> R4; template -> R4
provenance: benchmark-input-only
status: advisory
fix: number only true sequences, keep eyebrow labels for real categories, remove dividers inside one group, and let every tag carry an actual state or category
related:
history: 1 | 2026-08-28 | docs | initial registry registration, benchmark-informed structure-semantics entry in first-party wording
```

## CRAFT-11 — Declared scale conformance

```yaml
id: CRAFT-11
version: 1
title: Declared scale conformance
statement: Type sizes, spacing, and radii come from scales the project declares, each surface uses a small number of type steps, and nested radii stay concentric (observable). Off-scale values produce near-duplicate sizes and uneven rhythm that make hierarchy hard to read (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
threshold: type-steps-per-surface <= 6count
applicability-applicable: run has Fill output and a declared type, spacing, or radius scale (baseline or design declaration)
applicability-not-applicable: planning-only run (observable reason required)
applicability-blocked: no declared scale exists (the gap is a finding routed to design or baseline), or styling source unavailable
check-type: machine-detector
check-inputs: source style declarations compared against declared tokens. Computed font sizes per surface. Threshold reading: at most 6 distinct font sizes per surface, all from the declared type scale; spacing and radius values from declared tokens only; inner radius = outer radius minus the padding between them (never larger than the outer); no fixed base grid is mandated, the project declares its own scale
signals-rendered: near-duplicate font sizes within one surface. Inner corners rounder than their container
signals-source: raw px, rem, or ms literals outside token definitions. More type steps than the threshold. Radius tokens that ignore nesting
evidence-layers: source>=1
evidence-method: machine-measurement
severity-default: S1 / judgment
exceptions: third-party embedded widgets whose styles the product does not own. Data visualizations whose sizes follow data
false-positives: literals inside the token definition files themselves
owner: design -> R3; template -> R4
provenance: benchmark-input-only
status: advisory
fix: replace off-scale literals with the nearest declared token, merge near-duplicate type sizes into declared steps, and derive inner radii from outer radius minus padding.
related: CRAFT-06@1, A11Y-05@1
history: 1 | 2026-10-10 | docs | initial registration, benchmark-informed scale entry; the project declares its own scale and no fixed grid is imposed
```
