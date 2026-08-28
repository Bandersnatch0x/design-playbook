# First-party UX rule registry

Product-level declaration shared by the whole pipeline (read-only at run time; runs only produce audit rows and findings that reference it). Entry blocks below are structured field blocks validated by the product-level G8 self-check (`validate.py`, repo scripts).

- `schemaVersion: 1`
- Split rule: when the registry exceeds 30 entries or 3 families, split by family into per-family files plus an index and migrate the G8 cross-file checks at the same time.
- Machine-checkable face: `id / version / capability-domain / executes-in / authority / applicability-* / check-type / evidence-layers / severity-default / owner / provenance / status / related / overrides / supersedes`. Protocol face (read by reviewers, not gated): `title / statement / check-inputs / signals-* / evidence-method / exceptions / false-positives / fix / history`.
- Rule text is first-party original. External product names and third-party rule text never enter this registry.

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

## CRAFT-08 — Purposeless motion

```yaml
id: CRAFT-08
version: 1
title: Purposeless motion
statement: Every animation names the state change it explains and does not destabilize interaction (observable); motion without a state explanation draws attention away from the task (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface contains motion
applicability-not-applicable: run has no motion on the audited surface (observable reason required)
applicability-blocked: motion source or interaction trace was not included in review input
check-type: protocol-check
check-inputs: rendered motion observation; source motion implementation and reduced-motion handling; interaction trace when available
signals-rendered: bounce, elastic, looping, or entrance motion draws attention without communicating state
signals-source: animation targets layout properties, lacks reduced-motion handling, or has no named state transition
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: expressive game or immersive scene motion declared by product intent and kept clear of task controls
false-positives: micro-interaction transitions misread as decoration; decide by whether a named state change is present
owner: craft -> R4; design -> R4
provenance: first-party
status: advisory
fix: remove decorative motion or replace it with short transform or opacity feedback tied to a named state change
related: PERF-01@1
history: 1 | 2026-08-14 | docs | initial registry registration, migrated from the craft-guard detector protocol six-field block
```

## A11Y-01 — Accessible names, roles, and states

```yaml
id: A11Y-01
version: 1
title: Accessible names, roles, and states
statement: Interactive elements expose accessible name, role, and state plus a reachable keyboard path at the declared viewport (observable); missing names or keyboard dead ends block assistive-technology users from perceiving and operating the surface (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: hard-constraint
applicability-applicable: run has Fill output containing interactive elements
applicability-not-applicable: planning-only run, or a static non-interactive display surface (observable reason required)
applicability-blocked: a11y tree capture or keyboard walkthrough evidence unavailable
check-type: protocol-check
check-inputs: a11y tree capture; keyboard interaction walkthrough; source semantic bindings
signals-rendered: nodes without accessible name or role; keyboard traps; focus loss; material omissions the tree cannot prove (contrast, hit area, motion safety are findings, never silent passes)
signals-source: interactive elements without semantic bindings or focus management
evidence-layers: rendered>=1, source>=1
evidence-method: runtime-observation
severity-default: S3 / fact
exceptions: explicit legacy-surface exemptions recorded in the spec (each requires an owning declaration)
false-positives: decorative imagery correctly unnamed; hidden-at-runtime controls flagged by naive scans
owner: components -> R4; spec -> R2
provenance: first-party
status: advisory
fix: give each interactive element an accessible name and role, keep the keyboard path reachable, and attach findings to the owning user-risk L6 (ADR-0016 attach rule; do not auto-generate a11y L6 seeds)
related:
history: 1 | 2026-08-14 | docs | initial registry registration, first-party cross-cutting entry (accessibility)
```

## RESP-01 — Declared-viewport coverage

```yaml
id: RESP-01
version: 1
title: Declared-viewport coverage
statement: The implemented UI remains usable at every viewport the contract declares (observable); a surface that only works at one viewport fails users on declared target viewports (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: project-declaration
applicability-applicable: contract or capture contract declares target viewports and the run has Fill output
applicability-not-applicable: planning-only run with no Fill output (observable reason required)
applicability-blocked: no declared target viewport (the gap itself is a finding routed to D1/D2), or viewport capture unavailable at a declared viewport
check-type: protocol-check
check-inputs: capture contract viewport group; rendered captures per declared viewport; source responsive behavior
signals-rendered: layout breakage or unreachable actions at a declared viewport
signals-source: single-viewport-only implementation, fixed widths beyond declared maxima
evidence-layers: rendered>=1, source>=1
evidence-method: runtime-observation
severity-default: S2 / fact
exceptions: viewports explicitly declared out of scope in the contract
false-positives: pixel-perfect equality across viewports; only usable reachability is required
owner: spec -> R2; template -> R4
provenance: first-party
status: advisory
fix: implement or fix layout at each declared viewport; declare target viewports in the contract when the declaration is missing
related:
history: 1 | 2026-08-14 | docs | initial registry registration, first-party cross-cutting entry (responsive)
```

## I18N-01 — Interface language and localizability consistency

```yaml
id: I18N-01
version: 1
title: Interface language and localizability consistency
statement: User-visible copy keeps language, terminology, and formats consistent and does not block localization (observable); inconsistent terms and hard-coded formats raise localization and comprehension cost (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: platform-convention
applicability-applicable: contract declares an i18n field (such as i18n.*) or spec L1 declares a multilingual user base
applicability-not-applicable: single-language declaration with no locale-related field (observable reason required, e.g. single-language document interface with no i18n declaration)
applicability-blocked: copy inventory evidence needed for the decision is unavailable (for example rendered capture absent)
check-type: protocol-check
check-inputs: rendered copy sampling; source hard-coded copy locations; spec L1 terminology list
signals-rendered: mixed terminology; layout that cannot absorb copy expansion
signals-source: hard-coded date or number formats; user-visible copy outside the resource layer
evidence-layers: rendered>=1, source>=1
evidence-method: static-inspection
severity-default: S2 / judgment
exceptions: declared single-language product with a confirmed single-language user base
false-positives: in-code comments and developer-facing copy that is not user-visible (to be verified)
owner: spec -> R2; components -> R4
provenance: placeholder
status: advisory
fix: unify terminology to the spec L1 word list; route user-visible copy through the resource layer instead of hard-coding
related:
history: 1 | 2026-08-14 | docs | initial registry registration, placeholder entry with explicit applicability predicate (never silently skipped)
```

## PERF-01 — Perceived-performance feedback

```yaml
id: PERF-01
version: 1
title: Perceived-performance feedback
statement: Declared async operations carry perceived feedback proportionate to duration plus a timeout exit (observable); unindicated waits invite repeated triggers and erode trust (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: measured-threshold
applicability-applicable: spec L4 declares async operations and the run measurement layer is capturable
applicability-not-applicable: no async operation declared (observable reason required)
applicability-blocked: async declaration exists but the measurement provider is absent (perceived performance needs runtime measurement)
check-type: protocol-check
check-inputs: measurement-derived timing; interaction traces; spec L4 declarations
signals-rendered: unindicated long waits; feedback that does not match duration; no timeout exit
signals-source: trigger controls without busy or disabled bindings for in-flight operations
evidence-layers: measurement>=1, interaction>=1
evidence-method: runtime-observation
severity-default: S2 / judgment
exceptions: declared background tasks that report completion through notification instead of inline feedback
false-positives: operations shorter than the perception threshold being required to show feedback (to be verified)
owner: spec -> R2|R5
provenance: placeholder
status: advisory
fix: tier feedback by duration aligned with the craft Loading tiers declaration; timeouts get retry or cancel exits; in-flight triggers get busy state
related: CRAFT-08@1
history: 1 | 2026-08-14 | docs | initial registry registration, placeholder entry with explicit applicability predicate (never silently skipped)
```

## SEC-01 — Sensitive-operation safety experience

```yaml
id: SEC-01
version: 1
title: Sensitive-operation safety experience
statement: Sensitive data and dangerous operations have confirmation, undo, or audit exits (observable); unguarded dangerous actions cause irreversible loss (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: hard-constraint
applicability-applicable: domain or spec declares sensitive data or dangerous operations
applicability-not-applicable: declared scope has no sensitive surface (observable reason required, e.g. no sensitive operation added)
applicability-blocked: sensitivity cannot be determined from existing declarations (the declaration gap is itself a finding routed to D1)
check-type: protocol-check
check-inputs: interaction traces of dangerous operations; source confirmation and undo bindings; domain declarations
signals-rendered: dangerous operations without confirmation; sensitive values in clear text
signals-source: no confirm or undo binding on destructive triggers; no audit exit
evidence-layers: interaction>=1, source>=1
evidence-method: runtime-observation
severity-default: S3 / fact
exceptions: declared controlled-environment rehearsal operations backed by a domain declaration
false-positives: operations with a global undo stack being required to confirm twice (to be verified)
owner: domain -> R1; components -> R4
provenance: placeholder
status: advisory
fix: add confirmation or undo to dangerous operations; mask sensitive values; record audit exits in the domain declaration
related:
history: 1 | 2026-08-14 | docs | initial registry registration, placeholder entry with explicit applicability predicate (never silently skipped)
```

## COPY-01 — Active-voice control labels

```yaml
id: COPY-01
version: 1
title: Active-voice control labels
statement: Control labels state the action in active voice with a verb that names the visible result ("Save changes", not a generic submit word), and one action keeps one name across the whole flow (observable); mechanism words and drifting action names force users to guess what a control will do before pressing it (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface contains labeled actions or controls
applicability-not-applicable: planning-only run, or a display surface with no labeled control (observable reason required)
applicability-blocked: rendered copy or source string evidence unavailable
check-type: protocol-check
check-inputs: rendered control labels across the flow; source string resources; script-aware casing check — sentence case is a Latin-script convention, while CJK labels carry no case and are judged on verb-led directness instead
signals-rendered: labels naming a mechanism instead of the result (generic submit-style wording); the same action appearing under different names in different steps
signals-source: string resources holding synonyms for one action; Latin-script label strings cased as headlines where sentence case is the convention
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: control names fixed by the host platform's own convention (the platform convention outranks label rewording)
false-positives: a verified baseline brand voice that deliberately bends verb phrasing; record the baseline reference as the exception
owner: craft -> R4
provenance: benchmark-input-only
status: advisory
fix: rename each control to an active verb phrase stating its result, keep one name per action across the flow, and apply sentence case to Latin-script labels only (CJK labels stay verb-led without filler particles)
related: COPY-02@1
history: 1 | 2026-08-28 | docs | initial registry registration, benchmark-informed copy entry in first-party wording
```

## COPY-02 — User-side naming

```yaml
id: COPY-02
version: 1
title: User-side naming
statement: Interface nouns name the objects users control and recognize, not the system's implementation of them (observable); implementation vocabulary makes users translate between their task and the interface on every read (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface names objects or operations users act on
applicability-not-applicable: planning-only run, or a surface with no user-facing object naming (observable reason required)
applicability-blocked: rendered copy or source string evidence unavailable
check-type: protocol-check
check-inputs: rendered nouns on controls, headings, empty states, and messages; source string resources; spec L1 terminology list when declared
signals-rendered: storage or process vocabulary standing in for the user's object — a record, entity, or job where the user thinks in orders, photos, or reports
signals-source: user-visible strings reusing internal model, table, or field names verbatim
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: expert tools whose declared user base demonstrably speaks the implementation vocabulary (spec L1 declaration required)
false-positives: trade terms that look technical but are the user's own working language; verify against the declared user base before flagging
owner: craft -> R4
provenance: benchmark-input-only
status: advisory
fix: rename user-visible nouns to the objects users control (spec L1 word list when present) and keep implementation names inside code and logs; the bar holds across scripts — CJK nouns name the user's recognized object in the user's own words rather than loan-translating system terms, and Latin-script casing conventions never transfer to CJK naming
related: COPY-01@1
history: 1 | 2026-08-28 | docs | initial registry registration, benchmark-informed copy entry in first-party wording
```

## COPY-03 — Error-message tone

```yaml
id: COPY-03
version: 1
title: Error-message tone
statement: Error messages state what happened and the concrete next action in an even, direct tone (observable); apologetic, blaming, or vague error copy strands users at exactly the moment they need a recovery path (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the audited scope declares or renders error states
applicability-not-applicable: run has no error state in the audited scope (observable reason required)
applicability-blocked: error states cannot be reached or captured with the available evidence surface
check-type: protocol-check
check-inputs: rendered error states per failure path; source error strings and their recovery bindings
signals-rendered: error copy naming neither cause nor next action; apology or blame padding in place of the recovery step; one identical vague message across unrelated failures
signals-source: a single generic error string bound to many distinct failure paths; error strings with no associated retry, undo, or exit action
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: security-sensitive failures where the cause is deliberately withheld — still state what the user can do next
false-positives: terse diagnostics for a declared expert audience (spec L1); brevity is not vagueness when cause and action are both present
owner: craft -> R4
provenance: benchmark-input-only
status: advisory
fix: rewrite each error message to name the cause where safe and the next action always, drop apology and blame padding, and keep the tone even in Latin-script and CJK copy alike
related: COPY-02@1
history: 1 | 2026-08-28 | docs | initial registry registration, benchmark-informed copy entry in first-party wording
```

## A11Y-02 — Visible keyboard focus

```yaml
id: A11Y-02
version: 1
title: Visible keyboard focus
statement: Every keyboard-focusable element shows a visible focus indicator at the declared viewport (observable); an invisible focus position strands sighted keyboard users, who cannot tell where the next keystroke will land (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: hard-constraint
applicability-applicable: run has Fill output containing keyboard-focusable elements
applicability-not-applicable: planning-only run, or a static surface with no focusable element (observable reason required)
applicability-blocked: keyboard walkthrough or focused-state capture unavailable — an a11y tree alone cannot prove a visual property, so rendered or interaction evidence is required
check-type: protocol-check
check-inputs: keyboard traversal across the surface; focused-state captures per control archetype; source focus styling
signals-rendered: focus landing with no visible change; an indicator that is clipped, offscreen, or below perceivable contrast against its surroundings
signals-source: global focus outline suppression without an equivalent visible replacement
evidence-layers: rendered>=1, interaction>=1
evidence-method: runtime-observation
severity-default: S2 / fact
exceptions: elements intentionally removed from the tab order (the removal itself is judged under A11Y-01)
false-positives: platform-default indicators that render differently per platform or browser; visibility is the bar, styling uniformity is not
owner: template -> R4; craft -> R4
provenance: benchmark-input-only
status: advisory
fix: give every focusable element a visible focus style with sufficient contrast, never suppress a default outline without a replacement, and verify by keyboard traversal with focused-state captures
related: A11Y-01@1
history: 1 | 2026-08-28 | docs | initial registry registration, benchmark-informed accessibility entry in first-party wording; rendered plus interaction evidence demanded because an a11y tree cannot prove a visual indicator
```

## CRAFT-09 — Selector-specificity conflicts

```yaml
id: CRAFT-09
version: 1
title: Selector-specificity conflicts
statement: Style rules compose without fighting — no rule exists only to cancel or out-rank another, and adjacent blocks do not trade opposing spacing (observable); specificity duels and mutually cancelling padding or margin make every later edit unpredictable and leak visible seams to users (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
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
history: 1 | 2026-08-28 | docs | initial registry registration, benchmark-informed source-craft entry in first-party wording
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

## DECIDE-01 — Anti-default direction check

```yaml
id: DECIDE-01
version: 1
title: Anti-default direction check
statement: Every compare or explore tier direction selection answers the self-check "is this the direction I would produce for any similar brief?" with brief-specific evidence (observable); habit-default directions make unrelated products converge on one look and erase the identity the brief asked for (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: advisory-aesthetic
applicability-applicable: the run's decision report carries at least one compare or explore tier DD entry
applicability-not-applicable: point-fix or record-only run whose decision report carries no compare or explore tier DD entry (observable reason required)
applicability-blocked: decision report absent or unreadable, so the run's tier composition cannot be established
check-type: protocol-check
check-inputs: decision report DD entries at compare or explore tier; bound baseline identity declarations; the dated self-default direction observations recorded in this entry
signals-rendered: the selected direction matches a dated self-default profile — as of 2026-08 (dogfood evidence, refreshable observations): a light slate background with white cards and a teal or blue accent on admin surfaces, or a dark ops console with muted blue or cyan accents — while the DD entry records no brief fact that demands it
signals-source: selection rationale citing no spec item, baseline declaration, or brief fact — wording that would justify the same direction for any brief
evidence-layers: rendered>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: the brief or bound baseline explicitly declares one of the observed default directions as the wanted identity (the declaration outranks the anti-default heuristic)
false-positives: a conventional direction that the comparison matrix justified against brief axes; the check targets unexamined defaults, not convention itself
owner: design -> R3
provenance: first-party
status: advisory
fix: answer the self-check inside the DD rationale with brief facts, add at least one candidate that breaks the default profile before selecting, and refresh the dated observations when dogfood evidence shows the defaults moved
related:
history: 1 | 2026-08-28 | docs | initial registry registration, first-party decision-hygiene entry; default-direction examples recorded as dated, refreshable observations (2026-08, dogfood evidence)
```
