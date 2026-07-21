# ADR-0011: Reference intake is a conditional declaration input, not a gate

## Status

Accepted (2026-07-22). Boundary + first skill surface; no new machine gate.

## Context

Dogfood and research (see `docs/research/2026-07-21-open-design-projects.md`) show a recurring gap: users arrive with a screenshot, URL, existing design, or "like product X" taste note, but `ux-spec` and `ui-picker` only accept free-form chat. That leaves:

- inferred visual intent unmarked as observed vs guessed;
- Keep / Change / Do not copy boundaries unrecorded;
- license and brand risk invisible until Fill;
- no durable artifact that plan and ui-picker can consume without re-deriving from chat.

Open Design's `reference-design-contract` and open-codesign's reference decomposition both treat reference material as an **input package**. design-playbook already owns declarations + contracts; the missing piece is a **conditional intake contract** before `ux-spec`, not a visual Pass gate and not a code export path.

## Decision

1. **Conditional step only.** `reference-intake?` runs when the ask includes at least one of: local image/screenshot, design file path, URL, or an explicit product/brand analogy ("like Linear", "参考飞书"). No reference materials → skip with one-line narration.

2. **Declaration input, not Goal/Success/Evidence SSOT.** The contract records observations, inferences (labeled), Keep/Change/Do not copy, functional constraints for `ux-spec` (including always/ask/never hints), visual cues for `ui-picker`, license/brand risks, and unresolved questions. It does **not** replace `spec.md` L1→L6, does **not** write a decision report, and does **not** produce a Pass/Fail verdict.

3. **Artifact location (run-local).**
   ```text
   .scratch/<run>/reference/
     contract.md      # human-readable contract (template SSOT in skill references/)
     manifest.json    # source inventory: path/url, sha256, captured_at, tool
     assets/          # optional copied or linked local media
   ```
   Optional disposable `example.html` may land under `reference/` only as preview input. It is **never** a Fill source (same hard boundary as `preview/round-*.html`).

4. **Consumption map.**
   | Consumer | What it may read |
   | --- | --- |
   | `ux-spec` | functional constraints, non-goals implied by Do not copy, always/ask/never hints |
   | `plan` | pointer to `reference/contract.md`; description→spec map may cite reference ids |
   | `ui-picker` | Keep/Change visual cues, density/scene hints, risks |
   | Fill | **never** copies assets or example HTML; only implements report + spec |
   | `ui-evaluator` | may cite reference contract as supporting context for "copied forbidden pattern" findings; never as L6 proof |

5. **No new gate.** `validate_run.py` G1→G6 unchanged. Missing reference artifacts never fail a run. Presence is status/resume narration only (`scripts/run_status.py` stage `reference`).

6. **Authored-only.** Reference intake produces our artifacts about third-party material. It does not port third-party skills, design systems, or brand assets into the plugin ship surface (ADR-0003/0004).

## Consequences

- Orchestrator data flow becomes:
  `reference-intake? → ux-spec? → plan? → (native-craft?) → ui-picker → (preview*) → fill → craft-guard → (observe*) → ui-evaluator`
- New skill: `packages/design-playbook/skills/reference-intake/`.
- Future optional MCP provider (`decompose_reference`) may fill observed fields only; it must not write spec, decision report, or verdict. That provider is **out of scope for this ADR**.
- `run-manifest.json` freshness across the whole run remains a separate later ADR; this ADR only freezes the reference subtree.

## Non-goals

- Visual similarity score as Pass/Fail
- Automatic React/Vue/Flutter export from a screenshot
- Keyword-only skill auto-routing as the primary trigger
- Shipping third-party brand kits inside the plugin package
