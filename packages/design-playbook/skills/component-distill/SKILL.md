---
name: component-distill
description: Cross-run component backflow. Derive the reusable components that have recurred across iterated pages and render a propose-only promotion proposal for user adjudication. Use when iterated pages may have produced components worth promoting into DESIGN.md, when the same component keeps being reused across runs/scenes, or when the user asks what the pages have taught the design system. Report-only — never writes DESIGN.md or any authority.
---

# component-distill

Distill the recurring components out of iterated pages and propose promoting them into the project `DESIGN.md`. This is the **backflow** leg of the pipeline: `design-baseline` reads the baseline into pages once; this skill reads the pages back toward the baseline. It is **propose-only and user-gated** — it never writes `DESIGN.md` or any authority; promotion is a user decision (governance log) executed only by `design_baseline.py promote` (ADR-0012).

This is a **cross-run** review, not a step of a single Design I/O run. It reads prior runs' `decision-report.md` files and emits a proposal artifact for user adjudication.

## Authority boundary

| This skill owns | Does not own |
| --- | --- |
| Deriving recurring-component candidates across runs | Durable write to `DESIGN.md` (`design_baseline.py promote`, T-070) |
| Rendering the propose-only promotion proposal | The user promotion decision (governance log, user-only) |
| Reporting distance-to-threshold for below-threshold signals | Component/template selection for a run (`ui-picker`) |

## Deep module (SSOT for deterministic work)

Derivation lives in [`../../scripts/component_candidates.py`](../../scripts/component_candidates.py):

```python
candidate_view(reports_by_run) -> dict   # qualifying + below_threshold + gaps
```

`reports_by_run` maps a run id to its `decision-report.md` text. The module parses each report's `components:` block, counts `reuse <path>` / `extend <path>` as one recurrence of that component path (a `new` entry is a gap, never a candidate), and qualifies a candidate when it recurs across **distinct runs ≥ 3 AND distinct scenes ≥ 2**. Every group is returned — qualifying first, then below-threshold signals with their gap list — so distance to qualification is visible, never silent.

## Workflow

1. **Discover runs.** Scan the project's `.scratch/<run>/` dirs for a `decision-report.md`. List dirs without one as skipped (they contribute 0 references). If fewer than 2 runs carry a decision report, report that count and stop — backflow needs history to mean anything.
2. **Derive.** Build `reports_by_run` and call `candidate_view`. Read-only: parse, never mutate.
3. **Render the proposal** (markdown, report header `component-distill/v1`) at the invocation-level output path the caller names (not a single run's `design-baseline/` dir — this is a cross-run artifact). Sections:
   - **Inclusion manifest** — `run | status` (included / skipped + reason).
   - **Qualifying candidates** — one block per candidate: component path, recurrence, distinct runs, distinct scenes, the contributing references (`run / role / action / scene`), and a **decision slot** for the user (`promote | reject | defer`).
   - **Below threshold** — candidates approaching the threshold with their gap list (e.g. `distinct_runs 2 < 3`), so the distance is visible.
   - **Coverage** — `runs_with_components` / `total_references`, so an empty corpus reads as "no qualifying candidates + why", never silence.
4. **Adjudicate (user).** Present the proposal; the user marks each qualifying candidate. Record the decision as a governance event (agent may append `promotion_candidate_opened`; only the user's `promotion_decided` carries `promote`/`reject`/`defer`). This skill stops at the proposal — it does not write `DESIGN.md`.

**Done when:** the proposal artifact exists at the named output path, qualifying candidates carry full provenance and a decision slot, below-threshold signals carry their gaps, and nothing under the project `DESIGN.md` was touched.

## Scope fence

| In | Out → |
| --- | --- |
| Cross-run component recurrence → proposal | Durable `DESIGN.md` merge → `design_baseline.py promote` (T-070) |
| Report-only candidate derivation | Recording the user decision → promotion governance log |
| Token candidates (counted) | Token promotion into baseline → T-072 |
