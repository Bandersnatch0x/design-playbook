# OPP-01 — Enforce version↔inventory identity invariant

Status: resolved
Type: task
Source: product-surface roundtable 2026-08-03 (`.scratch/product-surface-roundtable-2026-08-03/roundtable.md`)

## Problem

`main`'s version and its installable inventory must always match the latest formal release (ADR-0015). In v0.10 prep the `run-review` command landed on `main` while version fields stayed `0.9.0`, so a clean marketplace install produced `design-playbook 0.9.0` with four commands including unreleased capability. The corrective commit `e5c9ed7` restored `main` to v0.9.1, but nothing prevents recurrence — the invariant is currently a narrative rule in ADR-0015, not a machine check.

## What to build

A machine-verified invariant that fails (in CI/validate) whenever the version and the shipped inventory disagree on `main`:

- Map version → expected inventory: skills count, commands (names), MCP servers, validator availability.
- Extend `scripts/validate.py` (or `release.py`) so a command/skill added to the package without a version bump that admits it (semver minor on the current release line) fails the gate.
- Establish the distribution inventory matrix (Claude marketplace, Codex marketplace, `npm pack` tarball, pi manifest) so each surface reports the same version/skills/commands/MCP inventory.

## Acceptance

- Red test: add a hypothetical 4th command while version stays `0.9.1` → validate FAILS.
- Green: current `main` (v0.9.1, 3 commands) passes.
- `npm pack --dry-run` inventory matches the manifest claims.
- The matrix is runnable in CI (static tarball part) and documented for the manual smoke part.

## Evidence

- `.scratch/product-surface-roundtable-2026-08-03/scan.md` P1 finding.
- ADR-0015.
- Corrective commit `e5c9ed7`.

## Kill criterion

If the public marketplace can reliably pin an immutable release tag AND `main` is provably never consumed by public installs, downgrade to a documentation rule. Otherwise the invariant must be enforced.

## Comments

- Created 2026-08-03 after the channel-model grill (ADR-0015).
## Answer

Implemented 2026-08-03 (`f712dfb`): `scripts/validate.py` gains a
version-vs-command inventory check (COMMAND_INVENTORY map; (0,9) → 3
commands, (0,10) → +run-review). Shipped command set must equal the
declared set for the plugin version; an unknown version line fails the
gate until an entry is declared. Red-to-green test
`test_extra_command_without_version_admission_fails`. Consequence:
feature/v0.10-run-review (version still 0.9.1, 4 commands) now fails
validate until bumped to 0.10.0 — intended release gate. The full
distribution inventory matrix (OPP-03) remains a follow-up.
