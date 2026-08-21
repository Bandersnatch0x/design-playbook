# ADR-0033: Audit & acceptance stages as user-selectable preferences

## Status

Accepted (2026-08-19).

## Context

The Design I/O pipeline currently treats every stage as agent-decided: fill and the preview confirmation (ADR-0008 floor) are hard, while `craft-guard`, `observe*`, and `ui-evaluator` run unconditionally or fall back only on provider absence. Users have asked to make the audit/acceptance stages optional for light runs. The risk is symmetric: silent skips already violate the "silent skips are illegal" run-profile rule, and `point-back.md` is a machine dependency — `validate_run.py` takes it as a positional argument, `aggregate_runs.py` reads it as the entry point, and `run_status` derives its verdict from it. Optional stages must therefore remain auditable and must never break the downstream chain or become a channel for forged audits.

## Decision

1. **Hard boundary.** Fill and the preview confirmation (ADR-0008 floor) are never skippable. `craft-guard`, `observe*`, and `ui-evaluator` become user-selectable.
2. **Choice mechanism.** An in-run user declaration takes priority. When the repository carries no preference record, the orchestrator asks once at first use. Repository-level values are team-authored input, not proof of current-user consent: when they affect the effective plan, the orchestrator confirms them once per session inside the existing tier-confirmation exchange.
3. **Storage.** Repository-level preferences are the default; a single-run declaration overrides them.
4. **Skip recording.** Every skip is recorded with a reason in the run-profile skip list (aligned with "silent skips are illegal"), and the run artifacts carry a limitation statement.
5. **point-back hard dependency.** If `ui-evaluator` is skipped, a minimal skeleton `point-back.md` is still generated, marked as not audited, so the downstream chain (`validate_run` positional argument, `aggregate_runs` entry point, `run_status` verdict source) never breaks.
6. **Preference files.** `.design-playbook/preferences.yaml` at the target repository root holds the team-shared default under version control; `.design-playbook/preferences.local.yaml` holds personal overrides. Local-scope write-back ensures the exact `.design-playbook/preferences.local.yaml` entry exists in the target repository's `.gitignore` before persisting personal choices.
7. **Injection mechanism.** Prose layer only: the orchestrating skill (`design-playbook` SKILL.md) reads preferences → trims stage execution → records skip reasons. The single routing authority of `run_profile.py` route (ADR-0032) is untouched; preferences are execution trimming after routing, never a routing input.
8. **Tier conflict.** An explicit user skip declaration authorizes a downgrade of the corresponding tier obligations (e.g. P2/P3 full-directory `craft-guard` evaluation, G11 sampling matrix). The exemption is automatic and recorded in the skip list: the "demotion needs the user" rule exists to prevent agent self-demotion, and a user's own declaration is the authorization.
9. **Scope.** The preference files contain exactly three booleans — `craft_guard`, `observe`, `ui_evaluator` — plus an "asked" status bit. Entry routing is not included; ADR-0032's fact-driven routing already covers it.
10. **First-ask timing.** The first ask merges into the existing tier confirmation dialogue (the one-time user tier confirmation in SKILL.md); no new interruption is added.
11. **Write-back.** A user declaration writes back as the new default preference unless the user explicitly says "this run only".
12. **Forgery boundary.** The skeleton point-back must carry exactly one machine-readable `audited: false` marker and a fixed limitation sentence. `validate_run --strict` and `--require-evidence` / `--require-coverage` reject skeleton runs and any present-but-ambiguous marker (duplicate, indented, commented, or malformed); `aggregate_runs` excludes both from audit-derived statistics and `run_status` never projects their verdict. Optionality is a convenience for honest users, not a channel for audit fraud.

## Consequences

- The four-layer preview floor (ADR-0008) remains fully mandatory; this decision touches nothing inside the preview transaction, integrity, or G5 floor path.
- G5/G6/G8 conditional gate logic is unchanged; gates still evaluate on whatever artifacts exist.
- Change surfaces introduced by this decision are listed as input for follow-up specs/tickets and are **not** implemented by this ADR:
  - orchestrating SKILL.md preference-reading section (ask-once, read, trim, skip-list recording, write-back);
  - skeleton `point-back.md` generation with the `audited: false` marker and fixed limitation sentence;
  - `validate_run` / `aggregate_runs` handling of `audited: false` (strict/require-flag rejection, aggregate presentation);
  - `doctor` displays the current effective preference state and corrupt layers for a target repository.
- Personal overrides (`preferences.local.yaml`) are protected by local-scope write-back ensuring their target-repository `.gitignore` entry; the repository tracks only the shared default.
- A skipped run is visibly degraded — skip list reason, limitation statement, and "not audited" status — rather than silently lighter.
