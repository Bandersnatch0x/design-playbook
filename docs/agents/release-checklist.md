# Release checklist - design-playbook

Manual gate. Automated checks (JSON, layout, frontmatter, clean surface, bundled MCP layout, version consistency incl. README badges, release notes present, seam test, adapter floor self-check) run via `python scripts/release.py` (dry-run) or `python scripts/release.py --apply` (creates the tag). Static portions also run in CI (`.github/workflows/ci.yml` -> `scripts/validate.py`); the session-level steps below remain manual.

## Validation surfaces

Three scripts overlap on version + bundled-MCP checks **by design**. Roles:

| Script | Purpose | Called by |
| --- | --- | --- |
| `scripts/validate.py` | Static structure gate (layout, bundled MCP, skill/command frontmatter, content residue, dogfood regression guards) | CI + `release.py` |
| `scripts/release.py` | Publish gate (tree clean, version consistency incl. README badges + release notes, then calls validate + seam + adapter floor, creates tag) | human release |
| `scripts/doctor.py` | Read-only diagnostic aggregator (one-stop: layout + version three-point + bundled MCP + launchers + floor self-check) | human |

`doctor.py` deliberately re-runs the version three-point comparison and the bundled-MCP check so a human gets one overview without invoking the other two scripts. The canonical rules live in `release.py` (version consistency, which also covers badges + release notes) and `validate.py` (bundled MCP); `doctor.py` mirrors them (see the `Mirrors ...` comments on `check_versions` / `check_mcp`). **One rule must not fork into two thresholds or two messages** — when changing either check, update both sites. If the overlap ever drifts in practice, extract a shared `scripts/_checks.py` (deferred from dedup-single-source ticket 02; the ~18-line overlap did not justify a new module yet).

## Automated release gate

```text
python scripts/release.py                    # dry-run: all gates, no side effects
python scripts/release.py --apply            # also creates the vX.Y.Z tag
python scripts/release.py --checks tree,tag  # run a subset (tree,version,validate,seam,adapter,tag)
```

Gates: working tree clean (untracked files also block) · versions match across plugin.json + marketplace.json (3 sites) **and** README.md / README-zh.md badges + semver · release notes exist at `docs/releases/vX.Y.Z.md` · `validate.py` green (incl. bundled MCP layout) · seam test green · adapter floor self-check green (bundled path) · tag absent **or already pointing at HEAD** (idempotent re-run passes; a tag pointing elsewhere fails).

## Prerequisites

- [ ] `git init` done; public GitHub remote created and pushed (`git remote add origin <url>`)
- [ ] `python scripts/release.py` dry-run PASSED

## Five-step gate (manual)

- [ ] **1. Plugin loads:** `claude --plugin-dir <abs>/packages/design-playbook` starts; `/reload-plugins` reports no errors; seven skills + three commands appear under the `design-playbook` namespace in `/help`. **Semi-automated (v0.4):** `scripts/doctor.py` checks the static counts (7 skills / 3 commands / plugin.json namespace); the dynamic `--plugin-dir` load + `/help` listing stay human (host slash, not automatable).
- [ ] **2. Six-gate dogfood:** `/design-playbook:design-io <real product UI ask>` passes all six gates (L5/L6 before UI; decision report before code; point-back findings; no Done-when skip; generality; recirculate closure). Log under `.scratch/design-playbook-v0/dogfood/`.
- [ ] **3. Validate:** `python scripts/validate.py` green (also in `release.py` and CI); `claude plugin validate` too if your Claude Code version has it.
- [ ] **4. Clean surface:** covered by `scripts/validate.py` (runtime surface; attribution files excluded).
- [ ] **5. Install docs copy-paste:** the root README install trio resolves - `/plugin marketplace add <owner>/<repo>` then `/plugin install design-playbook@design-playbook` succeeds in a second session/machine.

## Version + tag + publish (manual, irreversible)

- [ ] `plugin.json` + `marketplace.json` (3 sites) + README badge versions match (checked by `release.py`).
- [ ] `python scripts/release.py --apply` creates `vX.Y.Z` tag.
- [ ] `git push origin main && git push origin vX.Y.Z`.
- [ ] GitHub Release at `vX.Y.Z`; body = `docs/releases/X.Y.Z.md`.
- [ ] Smoke: a second session `/plugin marketplace add <owner>/<repo>` + install works end-to-end.

## "Not yet" (do not block v0.x)

- Automated CI / regression; community catalog (`@claude-community`) submission; `claude plugin validate` may be absent on some versions.
- i18n (CJK-first product; no i18n infra yet, not a v0 goal).
