# 06 - Release gate + first semver tag

**What to build:** A runnable manual release gate (five-step checklist) that must pass before tagging; then `git init` + public remote + first semver tag `v0.1.0`. Without this, the product stays `--plugin-dir`-only.

**Blocked by:** 01, 02, 03, 04, 05 (all resolved)

**Status:** partial - automatable parts done; git/remote/tag/smoke are human steps

- [x] Release checklist documented: `docs/agents/release-checklist.md` (five-step gate + version/tag + "not yet")
- [x] `plugin.json` carries explicit semver `version` (0.1.0); repo-root `marketplace.json` versions match
- [ ] `git init` + initial commit + public GitHub remote created (HUMAN)
- [ ] Release gate run green against the public remote (HUMAN - needs a real Claude session)
- [ ] `git tag v0.1.0` + `git push --tags` (HUMAN)
- [ ] Second machine/session can `/plugin marketplace add <owner>/<repo>` and install (HUMAN smoke)

## Implementation notes (done this turn)

- Wrote `docs/agents/release-checklist.md` - the manual five-step gate (plugin loads; six-gate dogfood; `claude plugin validate`; clean-surface `rg`; install-docs copy-paste) + version/tag steps + "not yet" list.
- Linked it from `product-workflow.md`.
- Verified semver 0.1.0 present and consistent across `plugin.json` + marketplace `metadata.version` + plugin entry `version`.
- No git repo exists yet; `git init` / commit / remote / tag are real state changes the agent should not make without explicit user go-ahead.

## Human steps (when ready)

1. `git init && git add -A && git commit -m "feat: design-playbook v0.1.0 - Design I/O plugin"`
2. Create public GitHub repo; `git remote add origin <url> && git push -u origin main`
3. Run `docs/agents/release-checklist.md` end-to-end (the five-step gate + second-session smoke).
4. `git tag v0.1.0 && git push --tags`.

## Review (standards + spec, inline)

- **Spec:** matches 06 decisions (manual gate, semver, git-remote hard prereq).
- **Standards:** checklist is checkable/exhaustive; semver consistent.
- **Commit:** this is the commit ticket - deferred to the human steps above.
