# examples

Self-authored samples for onboarding and dogfood. **Not** ports of any upstream playbook.

| File | Use |
| --- | --- |
| [ops-list-spec.md](ops-list-spec.md) | Minimal six-layer spec (ops delivery log) |
| [export-entry/](export-entry/) | P2 fixture run walkthrough: shaping session (S0-S6) + registry craft audit + six-block point-back with one Recirculate round; decision report carries R/C-tier DD entries (S2) |
| [export-upgrade/](export-upgrade/) | P3 fixture run walkthrough (S2; obligations completed in S6): E-tier DD entries with two preview confirmation rounds, provider candidate asset reference, R3 `dd:` challenge with supersedes revision + invalidated set, and baseline-drift stale review (keep exit); full-catalog craft audit + 10/10 sampling matrix |
| [dogfood/](dogfood/) | S6 dogfood fixture: a full P3 chain over this repo's own showcase queue surface (run-profile P3, shaping projection, E-tier DD with two preview rounds, R3 re-entry + one R4 repair, method-semantics manifest, full-catalog craft audit, 10/10 sampling matrix, verdict Pass) — static synthesized, no chromium |
| [rules-governance/](rules-governance/) | Paper governance-log walkthrough (S5): candidate opened from a 3-run / 2-context / 0-false-positive signal, then user promote -> advisory -> machine-enforced with the six criteria records |
| [settings-decision-report.md](settings-decision-report.md) | ui-picker decision report before code |
| [point-back-findings.md](point-back-findings.md) | evaluator output shape + recirculate |

2026-11-07 (T-158): the bundled `export-upgrade/` and `dogfood/` `design-baseline/state.json` files are **illustrative demo values** (stale relative-root bindings kept for the walkthrough). Complete `validate_run.py` acceptance re-verifies a present baseline, so executable tests copy the scenario to `<project>/.scratch/run` and bind a real baseline through `prepare`/`confirm` instead of trusting these files.

2026-11-07 (T-159): both fixtures' closed blocking findings now declare `criteria:` and carry the named `repair-evidence:` pair that complete acceptance derives from the finding. The pair halves are real files whose manifest `sha256` values match their bytes. The artifacts remain synthesized scripted-walkthrough JSONs (never renamed as native provider captures); their rows exist to exercise the machine contract, not to claim a real UI repair.

Agent-loaded SSOT remains `../skills/*/references/*`. These files are human-facing packs you can paste into a session.
