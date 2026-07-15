# Release checklist - design-playbook

Manual gate. Run **all** before tagging a release. Static portions (JSON, layout, frontmatter, clean surface) run automatically in CI (`.github/workflows/ci.yml` -> `scripts/validate.py`); the session-level steps below are still manual.

## Prerequisites

- [ ] `git init` done; public GitHub remote created and pushed (`git remote add origin <url>`)
- [ ] Working tree clean (`git status` clean)

## Five-step gate

- [ ] **1. Plugin loads:** `claude --plugin-dir <abs>/packages/design-playbook` starts; `/reload-plugins` reports no errors; six skills + three commands appear under the `design-playbook` namespace in `/help`.
- [ ] **2. Six-gate dogfood:** `/design-playbook:design-io <real product UI ask>` passes all six gates (L5/L6 before UI; decision report before code; point-back findings; no Done-when skip; generality; recirculate closure). Log under `.scratch/design-playbook-v0/dogfood/`.
- [ ] **3. Validate:** `python scripts/validate.py` green (also enforced in CI); `claude plugin validate` too if your Claude Code version has it.
- [ ] **4. Clean surface:** covered by `scripts/validate.py` (runtime surface; attribution files excluded).
- [ ] **5. Install docs copy-paste:** the root README install trio resolves - `/plugin marketplace add <owner>/<repo>` then `/plugin install design-playbook@design-playbook` succeeds in a second session/machine.

## Version + tag

- [ ] `plugin.json` `version` bumped (semver); repo-root `marketplace.json` `metadata.version` + plugin `version` match.
- [ ] `git tag vX.Y.Z && git push --tags`.
- [ ] Smoke: a second session `/plugin marketplace add <owner>/<repo>` + install works end-to-end.

## "Not yet" (do not block v0.x)

- Automated CI / regression; community catalog (`@claude-community`) submission; `claude plugin validate` may be absent on some versions.
