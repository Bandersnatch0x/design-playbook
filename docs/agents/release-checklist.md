# Release checklist - design-playbook

Manual gate. Automated checks (JSON, layout, frontmatter, clean surface, version consistency, seam test, adapter floor self-check) run via `python scripts/release.py` (dry-run) or `python scripts/release.py --apply` (creates the tag). Static portions also run in CI (`.github/workflows/ci.yml` -> `scripts/validate.py`); the session-level steps below remain manual.

## Automated release gate

```text
python scripts/release.py          # dry-run: all gates, no side effects
python scripts/release.py --apply  # also creates the vX.Y.Z tag
```

Gates: working-tree clean · plugin.json + marketplace.json (3 sites) version match + semver · `validate.py` green · seam test green · adapter floor self-check green · tag not pre-existing.

## Prerequisites

- [ ] `git init` done; public GitHub remote created and pushed (`git remote add origin <url>`)
- [ ] `python scripts/release.py` dry-run PASSED

## Five-step gate (manual)

- [ ] **1. Plugin loads:** `claude --plugin-dir <abs>/packages/design-playbook` starts; `/reload-plugins` reports no errors; six skills + three commands appear under the `design-playbook` namespace in `/help`.
- [ ] **2. Six-gate dogfood:** `/design-playbook:design-io <real product UI ask>` passes all six gates (L5/L6 before UI; decision report before code; point-back findings; no Done-when skip; generality; recirculate closure). Log under `.scratch/design-playbook-v0/dogfood/`.
- [ ] **3. Validate:** `python scripts/validate.py` green (also in `release.py` and CI); `claude plugin validate` too if your Claude Code version has it.
- [ ] **4. Clean surface:** covered by `scripts/validate.py` (runtime surface; attribution files excluded).
- [ ] **5. Install docs copy-paste:** the root README install trio resolves - `/plugin marketplace add <owner>/<repo>` then `/plugin install design-playbook@design-playbook` succeeds in a second session/machine.

## Version + tag + publish (manual, irreversible)

- [ ] `plugin.json` + `marketplace.json` (2 sites) versions match (checked by `release.py`).
- [ ] `python scripts/release.py --apply` creates `vX.Y.Z` tag.
- [ ] `git push origin main && git push origin vX.Y.Z`.
- [ ] GitHub Release at `vX.Y.Z`; body = `docs/releases/X.Y.Z.md`.
- [ ] Smoke: a second session `/plugin marketplace add <owner>/<repo>` + install works end-to-end.

## "Not yet" (do not block v0.x)

- Automated CI / regression; community catalog (`@claude-community`) submission; `claude plugin validate` may be absent on some versions.
- i18n (CJK-first product; no i18n infra yet, not a v0 goal).
