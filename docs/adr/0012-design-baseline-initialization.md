# ADR-0012: Existing-product UI requires a confirmed project design baseline

## Status

Accepted (2026-07-24). Amended same day: deep module `prepare` / `confirm` / `verify` with `state.json` as the sole gate artifact.

## Context

The pipeline can constrain function (`spec`), choose structure (`ui-picker`), and evaluate a result, but it does not initialize a project-specific visual authority. `reference-intake` only runs when the user explicitly supplies a screenshot, URL, design file, or product analogy; it is intentionally run-local and non-authoritative.

For a repository with existing pages, components, themes, and styles, that leaves the agent to infer visual language anew on every run. A new page may satisfy L1–L6 and generic craft rules while still looking unrelated to the existing product.

The ecosystem research originally classified every `DESIGN.md` as optional reference material. That conflated two different objects:

- a third-party/sample `DESIGN.md`, which is reference input;
- a first-party project `DESIGN.md`, which is a durable declaration of the product's visual baseline.

A split of inspect script + hand-written `confirm.json` was rejected as the long-term shape: it duplicated validation, allowed forged paths/hashes, and left draft generation non-executable.

## Decision

1. **Add conditional initialization `design-baseline?`.** For build/fix work that changes UI in a repository with meaningful existing first-party UI, run `design-baseline` before `reference-intake?`. Answer, review, diagnosis, and plan-only work do not trigger the gate. A true greenfield repository skips it.

2. **Canonical authority.** `<project-root>/DESIGN.md` is canonical. `.stitch/DESIGN.md` is a compatibility candidate. Different content at both paths is ambiguous and requires an explicit user choice; agents do not merge or create a third authority.

3. **Deep module interface.** One deterministic module owns path safety, scan, draft, durable write, and re-hash:

   ```python
   prepare(project_root, run_root)
   confirm(project_root, run_root, decision, reason=None)
   verify(project_root, run_root)
   ```

   Implementation: `packages/design-playbook/skills/design-baseline/scripts/design_baseline.py`.
   Sole gate artifact: `.scratch/<run>/design-baseline/state.json` (`schema: design-baseline/v1`).
   Statuses: `ready` | `needs_confirmation` | `waived` | `ambiguous`.
   Ready decisions use `decision.kind` ∈ {`existing`, `accepted`}.

4. **Draft from first-party evidence.** When missing or incomplete, `prepare` extracts design roles from theme/tokens, global styles/config, shared primitives, and representative pages. It writes only run-local `evidence.json` + `DESIGN.draft.md`, with observed/inferred labels, source hashes, confidence, contradictions, and gaps.

5. **No silent durable write.** `confirm(..., "accept")` is the only path that writes project `DESIGN.md` (atomic). `confirm(..., "waive", reason=...)` requires a non-empty user reason and does not write the baseline.

6. **Existing-product pre-Fill gate.** Fill is blocked until `verify` returns a `ready` or `waived` state. `verify` re-hashes baseline + sources and rejects forged/stale state. This is an orchestrator decision/confirmation gate, not a new `validate_run.py` G1–G6 criterion. A pending draft is not authority.

7. **Bind one baseline through the loop.** `ui-picker` cites verified baseline path + SHA-256 in its decision report. Fill consumes its roles/tokens/primitives. `craft-guard` and `ui-evaluator` report observable divergence back to `DESIGN.md`. The baseline is a declaration, never L6 runtime proof by itself.

8. **Keep external references separate.** Third-party/sample `DESIGN.md` remains `reference-intake` input and can produce Keep/Change/Do not copy notes. It never becomes project authority automatically.

## Consequences

- Orchestrator data flow becomes:
  `design-baseline? → reference-intake? → ux-spec? → plan? → (native-craft?) → ui-picker → (preview*) → fill → craft-guard → (observe*) → ui-evaluator`.
- New skill: `packages/design-playbook/skills/design-baseline/`.
- New run artifacts: `.scratch/<run>/design-baseline/{state.json,evidence.json?,DESIGN.draft.md?}`.
- `scripts/run_status.py` includes the baseline stage (`state.json`) for resume narration.
- Project consistency becomes an explicit declaration check instead of an implicit taste guess.
- Extraction can expose legacy inconsistency; it must preserve contradictions under gaps rather than average them into false authority.
- Agents may enrich draft wording (`[inferred confidence=…]`) but must not hand-author gate status, paths, or hashes.

## Rejected alternatives

- **Extend `reference-intake` to own the project baseline.** Rejected: reference intake is run-local, may contain third-party material, and is intentionally not a gate.
- **Always regenerate `DESIGN.md`.** Rejected: it would overwrite human authority and turn implementation accidents into policy.
- **Use only generic `ui-picker/references/design.md`.** Rejected: generic token discipline cannot encode a specific product's typography, density, shape, and component language.
- **Make `DESIGN.md` L6 evidence.** Rejected: a declaration describes what should hold; runtime evidence proves what actually happened.
- **Split inspect + agent-written `confirm.json`.** Rejected: forgeable hashes/paths, duplicated validation, non-executable draft generation.
