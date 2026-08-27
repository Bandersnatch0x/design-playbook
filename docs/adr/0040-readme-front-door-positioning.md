# ADR-0040: README front-door positioning

Accepted (grilling session, 2026-08-27).

## Context

The root READMEs were rewritten for v0.21.0 but still read like internal
docs: the pipeline diagram and its `?`/`*`/`†` marker legend arrived
before the install command, no section owned the selling points, and a
third of the body was contributor-facing (layout tree, maintainer
helpers, run-profile matrix). A survey of six high-traction comparable
projects (browser-use, cline, ollama, mem0, aider, SuperClaude) showed
the shared pattern: action within the first screen, sections ordered by
reader journey rather than internal architecture, and details collapsed
or linked away.

## Decision

1. **Target reader:** a Claude Code / Codex user who already ships UI
   with agents and distrusts unverified output. Not the general frontend
   developer, not primarily the team lead.
2. **Two headline selling points, in this order:**
   - **Evidence-forced acceptance** — the agent cannot grade its own
     homework (point-back, `audited: false` refusal, six gates green).
   - **One command → three artifacts** — `/design-io` lands spec,
     decision report, and point-back ledger with zero extra config.
   Pipeline predictability and ecosystem composability are secondary.
3. **Section order (both root READMEs, mirrored):** hero + tagline +
   badges → one-command/three-artifacts story → install → evidence
   section (screenshot gallery serves as proof) → pipeline diagram with
   the marker legend collapsed in `<details>` → skills/commands → the
   rest.
4. **Demoted from the front door:** layout tree and maintainer helpers
   become a one-line link to docs; the run-profile matrix collapses to a
   summary plus spec link; declarations & contracts fold into the
   pipeline section.
5. **Social proof:** badges must link to verifiable targets (npm page,
   license file). No download counts or star history until the numbers
   help rather than expose cold start.
6. **Demo media:** a real recorded `/design-io` terminal run is a
   follow-up asset; no stitched-screenshot GIF (cheap-looking).

## Consequences

- The prose-contract strings pinned by
  `tests/test_audit_preferences_prose.py` (audit legend wording,
  `audited: false`, `craft-guard†`, `ui-evaluator†`) stay in the file —
  inside the collapsed legend — while the evidence section restates the
  refusal semantics in plain language.
- Any future README restructure starts from this positioning instead of
  re-litigating it; changing the target reader or headline points means
  superseding this ADR.
- README edits must run the prose-contract test suite, not only
  `check_doc_links.py` (the v0.21.0 PR failed CI on exactly this).
