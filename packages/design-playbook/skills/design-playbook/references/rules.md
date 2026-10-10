# First-party UX rule registry

Product-level declaration shared by the whole pipeline (read-only at run time; runs only produce audit rows and findings that reference it). Entry blocks below are structured field blocks validated by the product-level G8 self-check (`validate.py`, repo scripts).

- `schemaVersion: 1`
- Split rule: when the registry exceeds 30 entries, or its entries span more than 3 capability-domain groups, split by group into per-group files plus an index, and migrate the G8 cross-file checks at the same time. ID prefixes are naming families, not split groups.
- Machine-checkable face: `id / version / capability-domain / executes-in / authority / applicability-* / check-type / evidence-layers / severity-default / owner / provenance / status / related / overrides / supersedes / threshold`. Protocol face (wording read by reviewers): `title / statement / check-inputs / signals-* / evidence-method / exceptions / false-positives / fix / history`; `evidence-method` is one of `expert-review | runtime-observation | static-inspection | machine-measurement`, and `statement`, `evidence-method`, `exceptions`, `false-positives` and `fix` are required.
- Exemption discipline (two layers; distinct from an entry's `exceptions` field, which is a rule-internal legitimate exception grounded in a declaration): a **run-level exemption** of an `advisory` rule is agent-recordable in the audit row or finding (`ID@version` + observable reason + evidence ref; a blank reason is illegal) and expires with the run. A **persistent exemption** of a machine-enforced rule is a user-only governance event — `exemption_granted` in `<project>/rules-governance.jsonl` pinning `ID@version` with rationale + risk — and whoever grants it must, in the same act, append the paired entry to the project decision log (`decisions.jsonl`, `field` = the rule ID): a governance-log exemption without its decision-log twin is an unrecorded governance decision. No calendar expiry; the exemption is re-reviewed on structural events only (rule version bump, supersession, or change of the declaration it rests on).
- Rule text is first-party original. External product names and third-party rule text never enter this registry.
- Authority semantics: hard-constraint and measured-threshold entries carry fact-class severity; measured-threshold entries carry a threshold field that is the single source for every number the pipeline uses for that rule; advisory-aesthetic entries carry judgment-class severity no higher than S2; usability-heuristic entries cover usability conventions that are neither taste nor measured, with severity no higher than S2; platform-convention entries stay at S2 or below.
- Threshold syntax: `threshold: <term> <op> <number><unit>; ...` with op one of `>= <= =` and unit one of `:1 px ms s % count`. Each term appears once. Prose explaining a number stays in `statement` or `check-inputs`.
- Entry text is version-pinned. Changing an entry's text without incrementing its
  `version` makes every `ID@version` exemption ambiguous, because the pin still
  resolves to the same version number over different words. A prose edit to an
  entry is a version bump plus a matching `history` line.

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
version: 2
title: Perceived-performance feedback
statement: Declared async operations carry perceived feedback in the tier the threshold assigns to their duration, plus a timeout exit (observable). Unindicated waits invite repeated triggers and erode trust (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: measured-threshold
threshold: placeholder-from = 300ms; indicator-from = 2s; timeout-at = 10s
applicability-applicable: spec L4 declares async operations and the run measurement layer is capturable
applicability-not-applicable: no async operation declared (observable reason required)
applicability-blocked: async declaration exists but the measurement provider is absent (perceived performance needs runtime measurement)
check-type: protocol-check
check-inputs: measurement-derived timing. Interaction traces. Spec L4 declarations. Threshold reading: under 300 ms no indicator; 300 ms to 2 s layout-stable placeholder; over 2 s indicator plus what is happening; over 10 s timeout with retry or cancel
signals-rendered: feedback tier that does not match measured duration. No timeout exit beyond 10 s
signals-source: trigger controls without busy or disabled bindings for in-flight operations
evidence-layers: measurement>=1, interaction>=1
evidence-method: runtime-observation
severity-default: S2 / fact
exceptions: declared background tasks that report completion through notification instead of inline feedback
false-positives: an operation measured once above a tier boundary due to cold start. Use the declared typical duration
owner: spec -> R2|R5
provenance: first-party
status: advisory
fix: map each async path to the tier in the threshold. Timeouts get retry or cancel exits. In-flight triggers get busy state. Missing duration declarations are findings, never a silent clear.
related: CRAFT-08@2, STATE-01@2
history: 1 | 2026-08-14 | docs | initial registry registration, placeholder entry with explicit applicability predicate (never silently skipped); 2 | 2026-10-10 | docs | threshold moved into the registry as single source; absent duration declaration no longer clears
```

## SEC-01 — Sensitive-operation safety experience

```yaml
id: SEC-01
version: 2
title: Sensitive-operation safety experience
statement: Every dangerous operation offers at least one proportionate safety exit. Reversible operations prefer immediate undo over a confirmation step. Irreversible or unexpected losses require a confirmation that states the consequence. Undo names what it reverses, shows its result on screen, and supports more than one step. Sensitive values are masked by default (observable). Unguarded irreversible actions cause permanent loss, while confirmation on every routine delete trains users to click through warnings (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: hard-constraint
applicability-applicable: domain or spec declares sensitive data or dangerous operations
applicability-not-applicable: declared scope has no sensitive surface (observable reason required, e.g. no sensitive operation added)
applicability-blocked: sensitivity or reversibility cannot be determined from existing declarations (the declaration gap is itself a finding routed to D1)
check-type: protocol-check
check-inputs: interaction traces of dangerous operations. Source confirmation and undo bindings. Domain declarations of reversibility
signals-rendered: an irreversible operation with no confirmation. A reversible routine delete gated by a confirmation instead of undo. Undo that does not say what it reverses, or whose result lands off screen without being revealed. Single-step undo where a sequence was performed. Sensitive values in clear text
signals-source: destructive triggers with neither a confirmation nor an undo binding. No audit exit where the domain declares one
evidence-layers: interaction>=1, source>=1
evidence-method: runtime-observation
severity-default: S3 / fact
exceptions: declared controlled-environment rehearsal operations backed by a domain declaration. Assistive or simplified modes declared in the spec may require double confirmation
false-positives: a global undo history that covers the operation outside the visible surface. Verify the history before flagging
owner: domain -> R1; components -> R4
provenance: first-party
status: advisory
fix: classify each dangerous operation as reversible or irreversible in the domain declaration. Give reversible ones labeled multi-step undo that reveals its result. Give irreversible ones a consequence-stating confirmation. Mask sensitive values.
related: SEC-02@1
history: 1 | 2026-08-14 | docs | initial registry registration, placeholder entry with explicit applicability predicate (never silently skipped); 2 | 2026-10-10 | docs | resolve statement-versus-signal conflict (any proportionate exit), add undo quality, align with domain declaration of reversibility
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
version: 2
title: Error-message tone
statement: Error messages state what happened and the concrete next action in an even, direct tone (observable); apologetic, blaming, or vague error copy strands users at exactly the moment they need a recovery path (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: usability-heuristic
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
history: 1 | 2026-08-28 | docs | initial registry registration, benchmark-informed copy entry in first-party wording; 2 | 2026-10-10 | docs | authority recalibrated to usability-heuristic: a usability convention, neither taste nor a measured threshold
```

## A11Y-02 — Visible keyboard focus

```yaml
id: A11Y-02
version: 2
title: Visible keyboard focus
statement: Every keyboard-focusable element shows a visible focus indicator at the declared viewport (observable); an invisible focus position strands sighted keyboard users, who cannot tell where the next keystroke will land (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: hard-constraint
threshold: focus-contrast >= 3:1; focus-outline >= 2px
applicability-applicable: run has Fill output containing keyboard-focusable elements
applicability-not-applicable: planning-only run, or a static surface with no focusable element (observable reason required)
applicability-blocked: keyboard walkthrough or focused-state capture unavailable — an a11y tree alone cannot prove a visual property, so rendered or interaction evidence is required
check-type: protocol-check
check-inputs: keyboard traversal across the surface; focused-state captures per control archetype; source focus styling
signals-rendered: focus landing with no visible change; an indicator that is clipped, offscreen, or below perceivable contrast against its surroundings
signals-source: global focus outline suppression without an equivalent visible replacement
evidence-layers: rendered>=1, interaction>=1
evidence-method: runtime-observation
severity-default: S3 / fact
exceptions: elements intentionally removed from the tab order (the removal itself is judged under A11Y-01)
false-positives: platform-default indicators that render differently per platform or browser; visibility is the bar, styling uniformity is not
owner: template -> R4; craft -> R4
provenance: benchmark-input-only
status: advisory
fix: give every focusable element a visible focus style meeting the threshold. Never suppress a default outline without a replacement (suppression without replacement is blocking). A clipped or low-contrast indicator may be graded S2 by the evaluator. Verify by keyboard traversal with focused-state captures.
related: A11Y-01@1, A11Y-03@1
history: 1 | 2026-08-28 | docs | initial registry registration, benchmark-informed accessibility entry in first-party wording; rendered plus interaction evidence demanded because an a11y tree cannot prove a visual indicator; 2 | 2026-10-10 | docs | align default severity with the evaluator's blocking list; add measurable indicator threshold
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
evidence-layers: decision>=1
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

## STATE-01 — Pending feedback

```yaml
id: STATE-01
version: 2
title: Pending feedback
statement: Asynchronous triggers and data-loading regions present pending feedback that names the operation while it runs (observable); a silent trigger or a bare anonymous spinner leaves users guessing whether the action registered and whether waiting is safe (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: usability-heuristic
applicability-applicable: run has Fill output and the surface contains asynchronous triggers or data-loading regions (form submits, fetch-driven lists, uploads)
applicability-not-applicable: planning-only run, or every visible operation completes synchronously within the interaction (observable reason required)
applicability-blocked: pending states cannot be reached or captured with the available evidence surface
check-type: protocol-check
check-inputs: rendered pending states per asynchronous path; source request and state handling that gates the pending branch
signals-rendered: an asynchronous trigger with no visible pending feedback; a pending region that does not name what is loading or processing (a page-wide bare spinner covering one field's request)
signals-source: request handling with no pending branch bound to a rendered region; a pending flag consumed by nothing visible
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / fact
exceptions: operations that complete and surface their result within a single frame on the audited device (the pending state would only flash); background prefetch not tied to a visible user task
false-positives: progress already carried by a dedicated inline region that names the operation; a verified baseline prescribing silent local mutations
owner: craft -> R4
provenance: benchmark-input-only
status: advisory
fix: bind each asynchronous path to a pending region that names the operation, keep it scoped to the region it concerns, and resolve it deterministically into the result or failure state (PERF-01 covers the pacing of the feedback itself)
related: PERF-01@2
history: 1 | 2026-09-19 | docs | initial registry registration, benchmark-informed state-completeness entry in first-party wording; 2 | 2026-10-10 | docs | authority recalibrated to usability-heuristic: a usability convention, neither taste nor a measured threshold
```

## STATE-02 — Zero-data presentation

```yaml
id: STATE-02
version: 2
title: Zero-data presentation
statement: Data-fed collection surfaces declare what users see when the list is empty on first load and after filtering (observable); a blank region forces users to guess whether data is still loading, absent, or broken, and hides the next action (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: usability-heuristic
applicability-applicable: run has Fill output and the surface contains a collection or list display fed by data
applicability-not-applicable: planning-only run, or no data-fed collection display in the audited scope (observable reason required)
applicability-blocked: empty states cannot be reached or captured with the available evidence surface
check-type: protocol-check
check-inputs: rendered first-load-empty and filtered-empty presentations; source empty-branch handling for the collection's data source
signals-rendered: the collection region renders with no content and no hint while its data is empty; an empty presentation that offers no next action or explanation
signals-source: empty-result branches that render no region content; a data source with an empty path unhandled in the UI layer
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / fact
exceptions: create-first surfaces whose documented initial state is intentionally the empty canvas itself; the empty presentation is the specified product behavior (spec or verified baseline)
false-positives: a populated skeleton resolving within the declared loading flow (judged under STATE-01, not here)
owner: craft -> R4
provenance: benchmark-input-only
status: advisory
fix: give every data-fed collection an explicit empty presentation that says what the region is for and offers the next action, visually distinct from the pending presentation (STATE-01) and from failure feedback (STATE-03)
related: STATE-01@2, STATE-03@2
history: 1 | 2026-09-19 | docs | initial registry registration, benchmark-informed state-completeness entry in first-party wording; 2 | 2026-10-10 | docs | authority recalibrated to usability-heuristic: a usability convention, neither taste nor a measured threshold
```

## STATE-03 — Failure feedback

```yaml
id: STATE-03
version: 2
title: Failure feedback
statement: Failed asynchronous paths present recoverable feedback that names what failed and the next action — retry, undo, or exit — instead of failing silently to the console or surfacing a raw exception trace (observable); users stranded at a failure without a recovery path abandon the flow or retrigger the damage (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: usability-heuristic
applicability-applicable: run has Fill output and the audited scope declares or triggers failure paths for asynchronous operations
applicability-not-applicable: run has no asynchronous failure path in the audited scope (observable reason required)
applicability-blocked: failure states cannot be reached or captured with the available evidence surface
check-type: protocol-check
check-inputs: rendered failure states per asynchronous failure path; source error handling bound to request or mutation paths
signals-rendered: an asynchronous action fails with no rendered feedback beyond the previous state; a raw exception or stack trace rendered to the user; a failure banner offering no retry, undo, or exit action
signals-source: error branches that only log to the console; a catch path with no bound rendered region or recovery action
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / fact
exceptions: diagnostic or operator surfaces where raw detail is the declared point (spec L1 or verified baseline); security-sensitive withholdings — still state what the user can do next even when the cause is withheld
false-positives: failure feedback deferred by a declared retry policy that still lands in a rendered recovery state; terse diagnostics for a declared expert audience (spec L1)
owner: craft -> R4
provenance: benchmark-input-only
status: advisory
fix: bind each failure path to a rendered recovery region naming what failed where safe and what to do next, with retry or exit always present; keep the tone even (COPY-03 covers the message wording)
related: COPY-03@2, STATE-01@2
history: 1 | 2026-09-19 | docs | initial registry registration, benchmark-informed state-completeness entry in first-party wording; 2 | 2026-10-10 | docs | authority recalibrated to usability-heuristic: a usability convention, neither taste nor a measured threshold
```

## A11Y-03 — Contrast in every declared appearance

```yaml
id: A11Y-03
version: 1
title: Contrast in every declared appearance
statement: Text and essential non-text elements meet the contrast floors below in every appearance the product declares (light, dark, increased contrast), and an increased-contrast variant exists whenever the default appearance misses a target (observable). Low-contrast text and controls are unreadable for low-vision users and in bright ambient light (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: measured-threshold
threshold: text-contrast >= 4.5:1; large-text-contrast >= 3:1; nontext-contrast >= 3:1; large-text-from = 24px; large-bold-text-from = 19px
applicability-applicable: run has Fill output containing text or essential non-text elements, evaluated once per declared appearance
applicability-not-applicable: planning-only run, or a surface with no text and no essential non-text element (observable reason required)
applicability-blocked: color tokens or computed colors for a declared appearance cannot be read, or the increased-contrast preference cannot be emulated during capture
check-type: machine-detector
check-inputs: computed foreground and background color pairs per text node and essential non-text element. Declared appearance set from the baseline or contract. Captures under each appearance preference, including the increased-contrast and forced-colors preferences. Threshold reading: body text (under 24 CSS px regular, or under 19 CSS px at weight 700 and above) >= 4.5:1; large text >= 3:1; essential non-text (control boundaries needed to find the control, focus indicators, state icons, chart marks that carry meaning) >= 3:1 against adjacent colors; recommended target for small body text 7:1
signals-rendered: any measured pair below its floor in any declared appearance. Text over images or gradients without a guaranteed backing. An increased-contrast preference that changes nothing while the default misses the target
signals-source: color tokens defined for one appearance only. Muted or placeholder tokens used as body text color. No increased-contrast or forced-colors branch while defaults miss the target
evidence-layers: rendered>=1, source>=1
evidence-method: machine-measurement
severity-default: S2 / fact
exceptions: disabled controls, purely decorative text and imagery, and logotypes. Placeholder text still counts when it is the only label
false-positives: anti-aliased edge pixels sampled instead of glyph color. Overlays measured against the wrong backdrop. Measure the composited backdrop under the text box
owner: design -> R3; components -> R4; baseline -> R3
provenance: benchmark-input-only
status: advisory
fix: raise the failing token to meet its floor in every declared appearance. Define light, dark, and increased-contrast values for every color role. Route text color through role tokens, never through muted or decorative tokens.
related: A11Y-02@2, A11Y-06@1
history: 1 | 2026-10-10 | docs | initial registration, benchmark-informed contrast entry in first-party wording; numeric floors are this registry's own rule
```

## A11Y-04 — Hit-target size

```yaml
id: A11Y-04
version: 1
title: Hit-target size
statement: Every interactive target offers a hit area at least the floor below, and touch-primary viewports meet the larger target (observable). Small targets cause mis-taps and exclude users with limited dexterity (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: measured-threshold
threshold: hit-area-floor >= 24px; touch-target >= 44px
applicability-applicable: run has Fill output containing interactive targets at a declared viewport
applicability-not-applicable: planning-only run, or a static surface with no interactive target (observable reason required)
applicability-blocked: page probe measurement status is blocked or unmeasured at a declared viewport
check-type: machine-detector
check-inputs: page probe tap rows per declared viewport. Source hit-area styling (padding, pseudo-element expansion). Threshold reading: floor 24 x 24 CSS px hit area for every interactive target (single source with the evidence runtime tap probe constant); target 44 x 44 CSS px on viewports the contract declares touch-primary
signals-rendered: probe tap rows whose shorter edge is under the floor. Touch-primary viewports with targets under the target size on the primary path
signals-source: icon buttons sized to the glyph with no padding or hit-area expansion. Adjacent targets whose expanded areas overlap
evidence-layers: rendered>=1, measurement>=1
evidence-method: machine-measurement
severity-default: S2 / fact
exceptions: inline links inside running text. A target under the floor whose 24 CSS px circle centered on it intersects no other target. Targets whose size is fixed by the host platform
false-positives: visually small targets with an invisible expanded hit area. Measure the hit area, not the painted box
owner: components -> R4; template -> R4
provenance: benchmark-input-only
status: advisory
fix: expand the hit area with padding or a pseudo-element to meet the floor, and the target size on touch-primary viewports, without enlarging the glyph. Keep at least the floor of spacing between adjacent targets.
related: A11Y-01@1
history: 1 | 2026-10-10 | docs | initial registration, registers the tap-size threshold already enforced by the evidence runtime so the rule and the code share one number
```

## A11Y-05 — Readable text size and scaling

```yaml
id: A11Y-05
version: 1
title: Readable text size and scaling
statement: User-readable text renders at or above the size floor, avoids thin weights at small sizes, and remains complete when text is enlarged to 200 percent (observable). Tiny or thin text and layouts that clip under zoom lock out low-vision users (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: measured-threshold
threshold: latin-text-min >= 11px; cjk-text-min >= 12px; thin-weight-min-size >= 16px; text-zoom >= 200%
applicability-applicable: run has Fill output containing user-readable text
applicability-not-applicable: planning-only run, or a surface whose only text is decorative or logotype (observable reason required)
applicability-blocked: computed font sizes or a 200 percent text-zoom capture are unavailable
check-type: machine-detector
check-inputs: computed font size and weight per text node. Capture at 200 percent text zoom per declared viewport. Source type tokens. Threshold reading: Latin-script text >= 11 CSS px; CJK text >= 12 CSS px; weights under 400 not used below 16 CSS px; at 200 percent text zoom no user-readable text is clipped, truncated without a way to read the rest, or overlapping
signals-rendered: text nodes under the floor. Thin weights at small sizes. Clipped, overlapping, or silently truncated text at 200 percent zoom
signals-source: type tokens below the floor. Fixed-height containers around text. Font sizes in units that ignore user text scaling
evidence-layers: rendered>=1, source>=1
evidence-method: machine-measurement
severity-default: S2 / fact
exceptions: legal fine print that the domain declaration requires verbatim and is also available at full size. Decorative text marked hidden from assistive technology
false-positives: superscript and subscript glyphs measured as body text. Judge the base run
owner: design -> R3; template -> R4
provenance: benchmark-input-only
status: advisory
fix: raise type tokens to the floor, replace thin weights at small sizes, and let containers grow or wrap so enlarged text stays complete.
related: CRAFT-11@1, CRAFT-06@1
history: 1 | 2026-10-10 | docs | initial registration, benchmark-informed text-size entry; numeric floors are this registry's own rule
```

## A11Y-06 — Color is never the only signal

```yaml
id: A11Y-06
version: 1
title: Color is never the only signal
statement: Every state, category, or required action conveyed by color is also conveyed by text, shape, icon, pattern, or position (observable). Color-only meaning is lost to users with color-vision deficiency and in monochrome or forced-color modes (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: hard-constraint
applicability-applicable: run has Fill output that encodes state, category, validity, or risk with color
applicability-not-applicable: planning-only run, or a surface where color encodes no meaning (observable reason required)
applicability-blocked: rendered captures or source state bindings unavailable
check-type: protocol-check
check-inputs: rendered states and chart legends inspected in a grayscale capture. Source bindings between state and visual treatment
signals-rendered: in a grayscale capture two states, categories, or validity results become indistinguishable. Links distinguished from body text by hue alone. Chart series separable only by hue
signals-source: state classes that change only a color property. Error fields with a red border and no message or icon
evidence-layers: rendered>=1, source>=1
evidence-method: runtime-observation
severity-default: S2 / fact
exceptions: decorative color with no meaning. Color pickers and swatches whose subject is the color itself
false-positives: a redundant cue present but outside the captured crop. Check the full component before flagging
owner: domain -> R1; components -> R4; design -> R3
provenance: benchmark-input-only
status: advisory
fix: pair each color meaning with a text label, icon, shape, or pattern. Underline or otherwise mark links in running text. Give chart series distinct markers or direct labels.
related: A11Y-03@1, CRAFT-04@1
history: 1 | 2026-10-10 | docs | initial registration, benchmark-informed redundancy entry in first-party wording
```

## SEC-02 — Confirm and dismiss semantics

```yaml
id: SEC-02
version: 1
title: Confirm and dismiss semantics
statement: Temporary views (dialogs, sheets, popovers, confirmation prompts) can always be dismissed safely, the Escape key cancels them, the Return key triggers only a non-destructive default, and a destructive action is never the default or the sole visually primary control (observable). Wrong defaults turn a reflexive keypress into data loss (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: hard-constraint
applicability-applicable: run has Fill output containing a dialog, sheet, popover, or confirmation prompt
applicability-not-applicable: planning-only run, or no temporary view in the audited scope (observable reason required)
applicability-blocked: keyboard walkthrough of temporary views unavailable
check-type: protocol-check
check-inputs: keyboard walkthrough (Escape, Return, Tab order) of every temporary view. Source button roles and default bindings
signals-rendered: Escape does nothing or commits. Return triggers a destructive control. A destructive confirmation with the destructive control focused by default. No visible cancel path. Confirm labels that do not name the consequence (generic yes, OK, or confirm wording). Closing a view with unsaved user content discards it without a choice. A second dialog stacked over a first
signals-source: destructive buttons bound to the default or primary variant. Missing Escape handler on dialog roots. Cancel styled as the primary variant while confirming a destructive action the user did not deliberately choose
evidence-layers: interaction>=1, source>=1
evidence-method: runtime-observation
severity-default: S3 / fact
exceptions: when the user deliberately chose a destructive command and the prompt only restates it, the confirm control may keep neutral styling and Return may confirm, provided the action is reversible or its consequence is stated. Purely informational notices may use a single acknowledgment control
false-positives: Escape intercepted by an inner editor that consumes it first. Verify the second Escape reaches the view
owner: components -> R4; domain -> R1
provenance: benchmark-input-only
status: advisory
fix: bind Escape to cancel on every temporary view. Give the default role only to a non-destructive control. Label confirm controls with the consequence verb. Offer save or discard when closing would lose user content. Never stack temporary views.
related: SEC-01@2, CRAFT-01@1, COPY-01@1
history: 1 | 2026-10-10 | docs | initial registration, benchmark-informed dialog semantics entry in first-party wording
```

## STATE-04 — Transient feedback

```yaml
id: STATE-04
version: 1
title: Transient feedback
statement: Transient notices never carry the only copy of a failure or a required action, stay readable long enough, pause while hovered or focused, are announced to assistive technology at a level matching their urgency, and routine successes stay quiet unless the action is significant (observable). Notices that vanish too fast, or that bury the one critical message among trivia, leave users unaware of what happened (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: usability-heuristic
threshold: notice-visible >= 5s; action-notice-visible >= 10s; concurrent-notices <= 1count
applicability-applicable: run has Fill output that renders transient notices (toasts, snackbars, inline flashes)
applicability-not-applicable: no transient notice in the audited scope (observable reason required)
applicability-blocked: notice timing or live-region semantics cannot be captured with the available evidence surface
check-type: protocol-check
check-inputs: interaction trace with notice appearance and disappearance timestamps. a11y tree live-region roles. Source notice configuration. Threshold reading: auto-dismissing notices stay visible >= 5 s and pause while hovered or focused; notices carrying an action (undo, retry) do not auto-dismiss before the action is taken or dismissed, or >= 10 s when they must expire
signals-rendered: a failure shown only in an auto-dismissing notice with no persistent state. Notices that disappear before the threshold or while focused. Every routine save confirmed with a notice. Several notices stacked at once
signals-source: notice duration below the threshold. Missing live-region role, or an assertive role on routine information
evidence-layers: interaction>=1, source>=1
evidence-method: runtime-observation
severity-default: S2 / judgment
exceptions: native desktop targets that route background events to the operating system notification area by native-craft declaration
false-positives: a notice that mirrors a persistent inline state already visible. The persistent state is the record
owner: craft -> R4; components -> R4
provenance: benchmark-input-only
status: advisory
fix: keep failures and required actions in a persistent region, and use the notice only as a pointer. Meet the timing threshold, pause on hover and focus, use a polite live region for information and an assertive one only for failures, and drop notices for routine success.
related: STATE-03@2, PERF-01@2
history: 1 | 2026-10-10 | docs | initial registration, benchmark-informed transient-feedback entry; timing numbers are this registry's own rule
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
