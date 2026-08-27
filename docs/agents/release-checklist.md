# Release checklist - design-playbook

Manual gate. Automated checks (JSON, layout, frontmatter, clean surface, bundled MCP layout, fixed npm release-group consistency, README badges, release notes present, seam test, adapter floor self-check) run via `python scripts/release.py` (dry-run) or `python scripts/release.py --apply` (creates the tag). Static portions also run in CI (`.github/workflows/ci.yml` -> `scripts/validate.py`); the session-level steps below remain manual.

## Validation surfaces

Four scripts cover release health. The first three overlap on version + bundled-MCP checks **by design**; `install_smoke.py` verifies the public channels from a fresh consumer environment. Roles:

| Script | Purpose | Called by |
| --- | --- | --- |
| `scripts/validate.py` | Static structure gate (layout, bundled MCP, skill/command frontmatter, content residue, dogfood regression guards, pinned Ruff on git-tracked `*.py`) | CI + `release.py` |
| `scripts/release.py` | Publish gate (tree clean, all main-package version sites plus DSH version/dependency lockstep, README badges + release notes, then validate + seam + adapter floor, creates tag) | human release + both publish workflows |
| `scripts/doctor.py` | Read-only diagnostic aggregator (one-stop: layout + version three-point + bundled MCP + launchers + floor self-check) | human |
| `scripts/install_smoke.py` | Live public-channel consumer check (isolated Claude config + exact inventory + strict validation + MCP handshakes + npm install); emits JSON/Markdown evidence | human after public main/npm update |

`doctor.py` deliberately re-runs the version three-point comparison and the bundled-MCP check so a human gets one overview without invoking the other two scripts. The canonical rules live in `release.py` (version consistency, which also covers badges + release notes) and `validate.py` (bundled MCP); `doctor.py` mirrors them (see the `Mirrors ...` comments on `check_versions` / `check_mcp`). **One rule must not fork into two thresholds or two messages** — when changing either check, update both sites. The version-to-command inventory is the shared exception that already lives in `scripts/_checks.py` (ADR-0015 / OPP-01): `validate.py` and `doctor.py` both import it, so a new command can never pass one gate and fail the other.

## Automated release gate

```text
python scripts/release.py                    # dry-run: all gates, no side effects
python scripts/release.py --apply            # also creates the vX.Y.Z tag
python scripts/release.py --checks tree,tag  # run a subset (tree,version,validate,seam,adapter,tag)
```

Gates: working tree clean (untracked files also block) · versions match across plugin.json + marketplace.json + `.codex-plugin/plugin.json` + `packages/design-playbook/package.json` (5 main-package sites), `packages/dsh-design-playbook/package.json` has the same version, and its `design-playbook` dependency is exactly `^X.Y.Z` · README.md / README-zh.md badges + stable semver · release notes exist at `docs/releases/vX.Y.Z.md` · `validate.py` green (incl. bundled MCP layout and npm release-group policy) · seam test green · adapter floor self-check green (bundled path) · tag absent **or already pointing at HEAD** (idempotent re-run passes; a tag pointing elsewhere fails). Validation is non-mutating; maintainers edit every version field explicitly before tagging.

## Live install smoke

```text
python scripts/install_smoke.py
# optional explicit evidence location
python scripts/install_smoke.py --output-dir .scratch/design-playbook-v0/evidence/install-smoke-vX.Y.Z
```

Defaults come from the local package manifest and exact source inventory. The script creates a fresh `CLAUDE_CONFIG_DIR`, adds the documented HTTPS marketplace, installs at user scope, checks version/enabled state plus exact skills/commands/scripts/MCP sets, runs strict plugin validation, performs real `initialize` + `tools/list` handshakes against both installed MCP servers, installs the matching npm artifact in a clean consumer, then writes `result.json` and `result.md`. Successful runs remove the temporary install directory; failures retain it and record the path. This live network flow stays human-triggered; CI runs `tests/test_install_smoke.py` without public installs.

## Prerequisites

- [ ] `git init` done; public GitHub remote created and pushed (`git remote add origin <url>`)
- [ ] `python scripts/release.py` dry-run PASSED

## Five-step gate (manual)

- [ ] **1. Plugin loads:** `claude --plugin-dir <abs>/packages/design-playbook` starts; `/reload-plugins` reports no errors; eight skills + **version-line command inventory** (0.12+: 6 commands incl. `run-status`/`doctor`) appear under the `design-playbook` namespace in `/help`. **Semi-automated:** `scripts/doctor.py` checks static counts against `COMMAND_INVENTORY` (8 skills / N commands / plugin.json namespace); the dynamic `--plugin-dir` load + `/help` listing stay human (host slash, not automatable).
- [ ] **2. Six-gate dogfood:** `/design-playbook:design-io <real product UI ask>` passes all six gates (L5/L6 before UI; decision report before code; point-back findings; no Done-when skip; generality; recirculate closure). Log under `.scratch/design-playbook-v0/dogfood/`.
- [ ] **3. Validate:** `python scripts/validate.py` green (also in `release.py` and CI); `claude plugin validate` too if your Claude Code version has it.
- [ ] **4. Clean surface:** covered by `scripts/validate.py` (runtime surface; attribution files excluded).
- [ ] **5. Install docs copy-paste:** after public main/npm update, `python scripts/install_smoke.py` passes from an isolated config and writes JSON/Markdown evidence. Interactive `/help` remains a human check.

## One-time release automation setup

- [ ] npmjs.com `design-playbook` Trusted Publisher: GitHub owner `Bandersnatch0x`, repository `design-playbook`, workflow `release.yml`, environment `npm`, allowed action `npm publish`.
- [ ] npmjs.com `dsh-design-playbook` Trusted Publisher: same owner/repository/environment, workflow `release-dsh-bundle.yml`, allowed action `npm publish`.
- [ ] GitHub environment `npm`: restrict deployment to release tags and configure the desired reviewer policy.
- [ ] Protect `refs/tags/v*` from deletion and retargeting with a repository ruleset.
- [ ] Do not configure `NPM_TOKEN` / `NODE_AUTH_TOKEN`; both publish workflows use job-scoped GitHub OIDC with npm Trusted Publishing.
- [ ] After the first successful OIDC publish, disable traditional token publishing where appropriate and revoke obsolete npm automation tokens and GitHub secrets.

The requirements and the `/path/to/pi-switch` comparison are recorded in `.scratch/design-playbook-v0/research/npm-trusted-publishing.md`.

## Version + tag + publish (tag-triggered, irreversible)

- [ ] Main package version sites + README badges match; `dsh-design-playbook` has the same version and depends on exactly `^X.Y.Z` (checked by `release.py`, `validate.py`, and `doctor.py`).
- [ ] `python scripts/release.py --apply` creates `vX.Y.Z` tag.
- [ ] Atomically push the release commit and tag: `git push --atomic origin main vX.Y.Z`.
- [ ] Monitor both tag-triggered workflows. `release.yml` publishes and verifies `design-playbook`; `release-dsh-bundle.yml` waits for that exact registry version, then publishes and verifies `dsh-design-playbook`. Both inspect their own `npm pack --dry-run` artifact first.
- [ ] The main workflow waits for the exact DSH registry artifact and verifies its provenance before it creates the single GitHub Release from `docs/releases/vX.Y.Z.md`. The DSH workflow never creates a second Release.
- [ ] Verify provenance and `latest=vX.Y.Z` for both npm packages; the pi.dev gallery indexes `design-playbook` for the `pi-package` keyword.
- [ ] DSH package-only recovery (`dsh-design-playbook@X.Y.Z` already exists): `gh workflow run release-dsh-bundle.yml --ref vX.Y.Z -f tag=vX.Y.Z -f recovery=true`. It verifies registry + provenance and never republishes or owns the GitHub Release.
- [ ] DSH not published (main package already on npm, `dsh-design-playbook@X.Y.Z` absent — the DSH workflow failed before its npm publish): fresh tag runs fail closed on both sides (main workflow hits the registry collision; dispatch recovery rejects the absent npm version). Re-run the failed `release-dsh-bundle.yml` push run from the GitHub Actions UI — a re-run preserves the original push/publish semantics.
- [ ] Main publish run failed **before** npm publish (`design-playbook@X.Y.Z` absent on the registry): dispatch is recovery-only (`release_state.py`), and a UI re-run replays the workflow file from the original tag commit, so the only path is to fix the workflow on main, then move the tag to the fix commit and push it again (`git push origin :refs/tags/vX.Y.Z`, re-tag, push). Nothing else may have been published yet; otherwise the registry-collision rules below apply. v0.21.0 precedent: the publish run failed at release gates because `release.yml` never installed the pinned Ruff that `validate.py` requires.
- [ ] Shared Release recovery (both npm artifacts exist, GitHub Release missing): `gh workflow run release.yml --ref vX.Y.Z -f tag=vX.Y.Z -f recovery=true`. Fresh tag runs fail on any existing version instead of silently skipping it.
- [ ] Smoke: `python scripts/install_smoke.py` passes against public main + npm; retain or move its `result.json` / `result.md` under the release evidence directory.
- [ ] Sync `.scratch/design-playbook-v0/phase.md` **header** (`**Current:**` line: version, tag, Release URL, npm latest) — the phase table row alone is not enough; the header is a second write point and has drifted before (v0.8.0 header survived the v0.9.0 release).

## "Not yet" (do not block v0.x)

- Community catalog (`@claude-community`) submission; interactive `/help` inventory inspection remains human.
- i18n (CJK-first product; no i18n infra yet, not a v0 goal).
