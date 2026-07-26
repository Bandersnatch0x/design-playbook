# Craft detector protocol

Run all eight detectors for implemented UI. Inspect rendered UI at declared target viewports and relevant source. Generic detector taste never overrides a verified project baseline; safety, usability, and explicit declarations still do.

Record exactly one row per detector in `.scratch/<run>/craft-guard.md`:

```text
| ID | Status | Rendered evidence | Source evidence | Exception check | Positive fix |
| CRAFT-01 | clear|hit|blocked | observable or missing proof | source location or missing proof | applied exception or none | required for hit; `-` otherwise |
```

Allowed status is `clear`, `hit`, or `blocked`. `blocked` names missing proof. Detector rows are advisory: do not assign declaration source, severity, or verdict. `ui-evaluator` owns those decisions.

## CRAFT-01 — Primary hierarchy

**Purpose:** Detect absent or competing primary actions and regions.

**Rendered signals:** More than one element claims primary emphasis, or no action/region leads the scan.

**Source signals:** Multiple primary variants, equivalent emphasis tokens, or page structure without a main landmark.

**Legitimate exceptions:** Deliberate equal-choice comparison supported by spec or verified baseline.

**Owner hint:** `craft` for emphasis; `template` when shell composition causes conflict.

**Positive fix:** Preserve one scene-appropriate primary and make secondary actions recede through placement, density, or neutral treatment.

## CRAFT-02 — Repeated card wall

**Purpose:** Detect undifferentiated card grids replacing useful information structure.

**Rendered signals:** Most content appears as equal floating cards with no scanning hierarchy or task grouping.

**Source signals:** Repeated card wrappers applied to unrelated regions or list/table records without a card-specific interaction.

**Legitimate exceptions:** Browsable collections where each item is a genuinely independent object and the verified baseline uses cards.

**Owner hint:** `template` for scene structure; `craft` for visual weighting.

**Positive fix:** Use list, table, band, or unframed grouping that matches comparison and action needs; reserve cards for independent items.

## CRAFT-03 — Nested or floating containers

**Purpose:** Detect cards inside cards and page sections styled as decorative floating panels.

**Rendered signals:** Multiple nested borders, radii, shadows, or detached section surfaces obscure ownership.

**Source signals:** Card components nested for spacing, or full-width sections wrapped in decorative card primitives.

**Legitimate exceptions:** A real framed tool, modal, or repeated item nested within an unframed page region.

**Owner hint:** `template` for section composition; `components` for wrong primitive identity.

**Positive fix:** Flatten page regions, use spacing and dividers for grouping, and retain a frame only where interaction semantics require one.

## CRAFT-04 — One-note palette

**Purpose:** Detect hue dominance that erases semantic contrast and hierarchy.

**Rendered signals:** Backgrounds, surfaces, accents, and states rely on variations of one hue family.

**Source signals:** One color ramp fills unrelated semantic roles or repeated gradients replace neutral surfaces.

**Legitimate exceptions:** Verified monochrome brand systems with sufficient state, contrast, and hierarchy differentiation.

**Owner hint:** `design` for token roles; `craft` for emphasis distribution.

**Positive fix:** Keep brand color selective, restore neutral surfaces, and use semantic colors only for named roles.

## CRAFT-05 — Shape and pill overuse

**Purpose:** Detect excessive rounded containers and text pills where familiar controls fit.

**Rendered signals:** Most labels, actions, and containers share pill geometry or oversized rounding.

**Source signals:** Large border-radius tokens applied globally, or text-in-rounded-rectangle controls replacing icons, toggles, tabs, or badges.

**Legitimate exceptions:** Verified brand geometry or semantic chips/tags whose shape communicates grouping or status.

**Owner hint:** `components` for control identity; `design` for radius tokens; `craft` for repetition.

**Positive fix:** Use control-specific primitives and restrained radii; reserve pills for semantics that need compact grouping.

## CRAFT-06 — Type-scale mismatch

**Purpose:** Detect typography whose scale conflicts with container and workflow density.

**Rendered signals:** Hero-sized copy dominates compact panels, or hierarchy depends on oversized text instead of structure.

**Source signals:** Display tokens used in cards, toolbars, dashboards, or narrow controls without a true hero context.

**Legitimate exceptions:** Literal landing-page hero or verified expressive product surface with stable responsive fit.

**Owner hint:** `design` for type roles; `craft` for contextual hierarchy.

**Positive fix:** Match type role to container and task density, using structure and weight before display scale.

## CRAFT-07 — Text-as-control and icon misuse

**Purpose:** Detect verbose rounded text controls where familiar symbols or dedicated controls communicate better.

**Rendered signals:** Repeated Undo, Close, Save, formatting, color, or binary actions consume space as text buttons.

**Source signals:** Text buttons replace available icon buttons, swatches, segmented controls, toggles, or checkboxes.

**Legitimate exceptions:** Unfamiliar, high-risk, or ambiguous actions that require explicit text; accessibility names remain required for icons.

**Owner hint:** `components` for primitive choice; `craft` for density and recognition.

**Positive fix:** Use familiar icon/control primitives with accessible names and tooltips where recognition needs support.

## CRAFT-08 — Decorative or purposeless motion

**Purpose:** Detect motion that explains no state change or destabilizes interaction.

**Rendered signals:** Bounce, elastic, looping, or entrance motion draws attention without communicating state.

**Source signals:** Animation targets layout properties, lacks reduced-motion handling, or has no named state transition.

**Legitimate exceptions:** Expressive game or immersive scene motion declared by product intent and kept clear of task controls.

**Owner hint:** `craft` for motion purpose; `design` for motion tokens.

**Positive fix:** Remove decorative motion or replace it with short transform/opacity feedback tied to a named state change.
