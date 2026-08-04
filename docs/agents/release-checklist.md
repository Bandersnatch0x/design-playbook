# Release checklist - design-playbook

Manual gate. Automated checks (JSON, layout, frontmatter, clean surface, bundled MCP layout, version consistency incl. README badges, release notes present, seam test, adapter floor self-check) run via `python scripts/release.py` (dry-run) or `python scripts/release.py --apply` (creates the tag). Static portions also run in CI (`.github/workflows/ci.yml` -> `scripts/validate.py`); the session-level steps below remain manual.

## Validation surfaces

Four scripts cover release health. The first three overlap on version + bundled-MCP checks **by design**; `install_smoke.py` verifies the public channels from a fresh consumer environment. Roles:

| Script | Purpose | Called by |
| --- | --- | --- |
| `scripts/validate.py` | Static structure gate (layout, bundled MCP, skill/command frontmatter, content residue, dogfood regression guards) | CI + `release.py` |
| `scripts/release.py` | Publish gate (tree clean, version consistency incl. README badges + release notes, then calls validate + seam + adapter floor, creates tag) | human release |
| `scripts/doctor.py` | Read-only diagnostic aggregator (one-stop: layout + version three-point + bundled MCP + launchers + floor self-check) | human |
| `scripts/install_smoke.py` | Live public-channel consumer check (isolated Claude config + exact inventory + strict validation + MCP handshakes + npm install); emits JSON/Markdown evidence | human after public main/npm update |

`doctor.py` deliberately re-runs the version three-point comparison and the bundled-MCP check so a human gets one overview without invoking the other two scripts. The canonical rules live in `release.py` (version consistency, which also covers badges + release notes) and `validate.py` (bundled MCP); `doctor.py` mirrors them (see the `Mirrors ...` comments on `check_versions` / `check_mcp`). **One rule must not fork into two thresholds or two messages** — when changing either check, update both sites. The version-to-command inventory is the shared exception that already lives in `scripts/_checks.py` (ADR-0015 / OPP-01): `validate.py` and `doctor.py` both import it, so a new command can never pass one gate and fail the other.

## Automated release gate

```text
python scripts/release.py                    # dry-run: all gates, no side effects
python scripts/release.py --apply            # also creates the vX.Y.Z tag
python scripts/release.py --checks tree,tag  # run a subset (tree,version,validate,seam,adapter,tag)
```

Gates: working tree clean (untracked files also block) · versions match across plugin.json + marketplace.json + `.codex-plugin/plugin.json` + `package.json` (5 sites) **and** README.md / README-zh.md badges + semver · release notes exist at `docs/releases/vX.Y.Z.md` · `validate.py` green (incl. bundled MCP layout) · seam test green · adapter floor self-check green (bundled path) · tag absent **or already pointing at HEAD** (idempotent re-run passes; a tag pointing elsewhere fails).

## Live install smoke

```text
python scripts/install_smoke.py
# optional explicit evidence location
python scripts/install_smoke.py --output-dir .scratch/design-playbook-v0/evidence/install-smoke-vX.Y.Z
```

Defaults come from the local package manifest and exact source inventory. The script creates a fresh `CLAUDE_CONFIG_DIR`, adds the documented HTTPS marketplace, installs at user scope, checks version/enabled state plus exact skills/commands/MCP sets, runs strict plugin validation, performs real `initialize` + `tools/list` handshakes against both installed MCP servers, installs the matching npm artifact in a clean consumer, then writes `result.json` and `result.md`. Successful runs remove the temporary install directory; failures retain it and record the path. This live network flow stays human-triggered; CI runs `tests/test_install_smoke.py` without public installs.

## Prerequisites

- [ ] `git init` done; public GitHub remote created and pushed (`git remote add origin <url>`)
- [ ] `python scripts/release.py` dry-run PASSED

## Five-step gate (manual)

- [ ] **1. Plugin loads:** `claude --plugin-dir <abs>/packages/design-playbook` starts; `/reload-plugins` reports no errors; eight skills + four commands appear under the `design-playbook` namespace in `/help`. **Semi-automated (v0.4):** `scripts/doctor.py` checks the static counts (8 skills / 4 commands / plugin.json namespace); the dynamic `--plugin-dir` load + `/help` listing stay human (host slash, not automatable).
- [ ] **2. Six-gate dogfood:** `/design-playbook:design-io <real product UI ask>` passes all six gates (L5/L6 before UI; decision report before code; point-back findings; no Done-when skip; generality; recirculate closure). Log under `.scratch/design-playbook-v0/dogfood/`.
- [ ] **3. Validate:** `python scripts/validate.py` green (also in `release.py` and CI); `claude plugin validate` too if your Claude Code version has it.
- [ ] **4. Clean surface:** covered by `scripts/validate.py` (runtime surface; attribution files excluded).
- [ ] **5. Install docs copy-paste:** after public main/npm update, `python scripts/install_smoke.py` passes from an isolated config and writes JSON/Markdown evidence. Interactive `/help` remains a human check.

## Version + tag + publish (manual, irreversible)

- [ ] `plugin.json` + `marketplace.json` + `.codex-plugin/plugin.json` + `package.json` (5 sites) + README badge versions match (checked by `release.py`).
- [ ] `python scripts/release.py --apply` creates `vX.Y.Z` tag.
- [ ] `git push origin main && git push origin vX.Y.Z`.
- [ ] GitHub Release at `vX.Y.Z`; body = `docs/releases/X.Y.Z.md`.
- [ ] `cd packages/design-playbook && npm publish` — the pi.dev gallery indexes npm for the `pi-package` keyword, so skipping this leaves pi users on the previous version with no other signal. Check the tarball first with `npm pack --dry-run`.
- [ ] Smoke: `python scripts/install_smoke.py` passes against public main + npm; retain or move its `result.json` / `result.md` under the release evidence directory.
- [ ] Sync `.scratch/design-playbook-v0/phase.md` **header** (`**Current:**` line: version, tag, Release URL, npm latest) — the phase table row alone is not enough; the header is a second write point and has drifted before (v0.8.0 header survived the v0.9.0 release).

## "Not yet" (do not block v0.x)

- Community catalog (`@claude-community`) submission; interactive `/help` inventory inspection remains human.
- i18n (CJK-first product; no i18n infra yet, not a v0 goal).
