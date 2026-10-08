---
name: craft-guard
description: UI craft and feedback quality. Use when polishing product UI (motion, loading and error feedback) or when a page reads as AI slop.
---

# craft-guard

**Craft** declaration for cross-product quality: hierarchy, wait feedback, purposeful motion, CJK-safe type. Does not own business risk (`domain`) or token inventory (`design`).

When a verified design-baseline binding exists (`status: ready`), use that path as the project-specific visual baseline. Report clear divergence (density, type, spacing, shape, motion, or shared component treatment) to `ui-evaluator` with source set to the bound path. Do not replace valid project choices with this skill's generic taste defaults.

When a persistent contract v1 is bound for the run (`contract-bind.json` / `scripts/contract_v1.py`), honor decided visual and craft constraints from that contract and reject unknown contract schema versions. Do not invent page or component inheritance layers.

## Apply (checklist)

Treat as exhaustive for the surface under edit.

### Hierarchy and type

- One clear primary. Secondary recedes via density and space, not rainbow chrome.
- CJK UI uses the project Chinese stack (`var(--font-cn)` or equivalent).
- Brand solid + brand-gradient **≤ 3** emphasis hits per viewport. Neutrals carry the rest.

**Done when:** a cold reader can name the primary action and region in one glance.

### Loading tiers

```text
<300ms      no indicator
300ms–2s    skeleton (layout stable)
>2s         loader + what is happening
>10s        timeout + retry (or cancel)
```

**Done when:** every async path in scope maps to a tier with a next action on failure/timeout.

### Motion

- UI motion ≤ 300ms. Animate `transform` / `opacity` only.
- Each animation names the state change it explains.
- Honor `prefers-reduced-motion`. Keyboard-triggered actions stay free of decorative motion.

**Done when:** every motion in scope states the state change it explains.

### Replace AI slop with the target look

For implemented UI, evaluate registry-entry applicability predicates in [`../design-playbook/references/rules.md`](../design-playbook/references/rules.md). Use the subset declared by the active spec and contract, or the full catalog when none is declared. Run every entry whose predicate evaluates to `applicable` against rendered UI plus relevant source. Execution protocol and the row format live in [`references/detectors.md`](references/detectors.md). Write exactly one seven-column audit row per **applicable** entry to `.scratch/<run>/craft-guard.md`:

| ID@ver | Applicability | Predicate reason / missing proof | Result | Rendered evidence | Source evidence | Exception check | Positive fix |
| --- | --- | --- | --- | --- | --- | --- | --- |

`Applicability` is the entry's three-state predicate outcome: `applicable`, `not-applicable`, or `blocked`. **not-applicable and blocked both require an observable reason** (blank is invalid, never a silent skip). `Result` is `clear|hit` only for applicable rows, `-` otherwise; `Positive fix` is required on hit rows. Missing rendered or source proof is `blocked`, not a silent clear. Unknown registry IDs fail at this stage. Audit rows are advisory: record evidence, exception check, and positive fix. Leave declaration source, severity, and verdict to `ui-evaluator`.

The host model may have no vision (text-only input). Renders stay **path-bound**: the `Rendered evidence` column cites the artifact path; never read the image. Assertions run on the **text face**: HTML and CSS source, `a11y tree` text, and interaction-trace action records. An interaction trace is a Playwright trace **ZIP**. Unzip before reading; the artifact is not JSON. A no-vision run evaluates the same registry protocol this way without degrading it. Genuinely missing rendered proof still records `blocked` honestly.

| Push toward | Instead of default sludge |
| --- | --- |
| Accent on key noun + primary CTA | Purple–blue gradient wallpaper |
| Glass only on rare floating layers | Blur on every card |
| Project CJK stack | Inter and Roboto as Chinese body |
| Weighted modules | Equal white card grid |
| State-explaining motion | Bounce and elastic decoration |

[`references/craft.md`](references/craft.md), **required when the surface has L4 interactive zones** (per-zone hover and motion affordance, with its own Done when). Also holds edge craft (failure and permission feedback, rounded-corners and shadows, charts).

## Completion

**Done when:** hierarchy, every in-scope wait and fail path, and every animation pass their checks. If the surface has L4 interactive zones, every zone's affordance passes its checks (per `references/craft.md`). Implemented UI also records exactly one seven-column audit row for every registry craft entry whose applicability predicate evaluates to `applicable`, with no unexplained missing proof. Residual hits and blocked proof are handed to `ui-evaluator`. Audit rows do not assign source, severity, or verdict. Machine check right after writing craft-guard.md: `python scripts/g8_run_registry.py .scratch/<run>/craft-guard.md`.
