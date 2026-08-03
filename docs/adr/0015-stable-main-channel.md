# 0015 — Stable main channel

`main` is the **public stable distribution channel**: its installable inventory (version, skills, commands, MCP servers, docs) always equals the latest formal release. Unreleased capability stays on feature/release branches until the release gate passes; a **release transaction** promotes one identical release commit to `main`, the semver tag, and the public registries together. Before promotion, `main` remains the previous release.

## Why

`/plugin marketplace add <owner>/<repo>` resolves the repo's default branch, so `main` *is* the public install surface — not a private development branch. In v0.10 prep, `e714c57` landed the `run-review` command on `main` while the version fields stayed at `0.9.0`; a clean install then produced version `0.9.0` with four commands, including unreleased capability. This broke version-based support, rollback, and issue reproduction. The decision is hard to reverse (it changes branch/release policy), surprising without context (a future reader seeing `main` lag the feature branch would wonder why), and was a real trade-off: rolling-main and a separate stable branch were considered and rejected.

## Considered options

- **Rolling main** — `main` carries the next version under prerelease semantics; npm `latest` stays stable. Rejected: splits "what the public installs" from "what the repo says", and the version marker alone cannot prevent the same identity drift.
- **Separate stable branch/repo** — a dedicated stable branch for public installs. Rejected: requires explicit ref-path pinning in the install flow and doubles the channel gates; unnecessary while `main` can be kept release-safe.
- **Stable main (chosen)** — `main` always equals the latest release; feature/release branches hold unreleased work; gate-then-merge keeps the release transaction atomic.

## Consequences

- Unreleased work lives on `feature/*` → `release/vX.Y.Z`; `main` only receives the gated release commit.
- The current `main` was restored to the v0.9.1 inventory via a corrective commit (`e5c9ed7`); v0.10 `run-review` continues on `feature/v0.10-run-review`.
- README, command counts, and release notes on `main` describe the latest release only; next-surface docs live on the feature branch.
- `docs/releases/` keeps every released note on `main` (v0.9.1 note restored).
- Future enforcement: a version↔inventory invariant (OPP-01) should make this a machine check, not a narrative rule.