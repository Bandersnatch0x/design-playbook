# ADR-0009: Bundled MCP adapters inside the plugin package

## Status

Accepted (2026-07-20). Supersedes the *distribution* aspect of the ADR-0005 sibling split for the two MCP adapters; the sibling directories remain as compatibility launchers.

## Context

ADR-0005 split preview/evidence into optional sibling packages so the plugin package stayed a clean redistributable root. In practice that made install two-step: the plugin installs via the marketplace, but each adapter still needed a hand-written host MCP entry pointing into the repo — the "ghost dependency" cold-start pain (dx-feedback ③). Claude Code plugins support a plugin-root `.mcp.json` whose servers launch via `${CLAUDE_PLUGIN_ROOT}`, which the split layout could not use.

## Decision

1. Adapter runtimes move into the plugin package: `packages/design-playbook/mcp/{preview,evidence}/`. Shipping **self-authored** Python runtime is within ADR-0003's authored-only scope (the ban is on third-party corpus content, not on our own code).
2. `packages/design-playbook/.claude-plugin/` stays plugin.json-only (ADR-0006). MCP servers are declared in the plugin-root `.mcp.json` via `${CLAUDE_PLUGIN_ROOT}/mcp/...`, so a marketplace install gets `preview*`/`observe*` with zero manual MCP config.
3. `packages/design-playbook-{preview,evidence}/server.py` remain as thin runpy **compatibility launchers** for existing local configs; their READMEs label them as such. **Retained through v0.4.x; evaluated for sunset at v0.5** (compatibility-surface removal is not a patch/minor change — it needs a major-version decision window). Reopen triggers for the sunset call (dedup-single-source ticket 05): a user issue/PR showing active launcher dependency, loss of CI coverage, or non-trivial maintenance burden (coupling / security). No deprecation notice ships until a sunset is actually decided.
4. Root `.mcp.json` (repo-dev convenience) points at the bundled paths.

## Consequences

- `scripts/validate.py` gains a bundled-MCP gate (`.mcp.json` shape, both servers present, `${CLAUDE_PLUGIN_ROOT}` usage, runtime files exist).
- CI syntax-checks and smoke-runs the bundled paths and keeps the launchers covered.
- ADR-0008 enforcement-site paths updated to `mcp/preview/`.
- The orchestrator's absent→skip contract is unchanged: bundling removes the manual-config step, not the optionality (hosts without MCP support still skip `preview*`/`observe*`).
- Launch config is intentionally present in three forms (plugin `.mcp.json` / root `.mcp.json` / `mcp.example.toml` for manual hosts); sibling README JSON blocks should become pointers if they drift.

## Amendment (2026-09-28): `run_root` env channel is per-host, not symmetric

Issue 09 originally forwarded `DESIGN_PLAYBOOK_RUN_ROOT` with a **shared** shape — an `env_vars: ["DESIGN_PLAYBOOK_RUN_ROOT"]` name-passthrough mirrored into *both* manifests "for symmetry". That symmetry was wrong for the Claude side.

- **Codex** (`.codex-plugin/mcp.json`) has no workspace variable and no env interpolation, so a name-passthrough array (`env_vars`) is its only host-trusted channel. It keeps `env_vars` — unchanged.
- **Claude** (`.mcp.json`) has no `env_vars` key in its schema. The [directory submission](https://claude.com/docs/plugins/submit) validates `.mcp.json` against the documented MCP server schema, whose environment field is the `env` object with `${VAR}` / `${VAR:-default}` interpolation. Claude Code also launches stdio servers with a sanitized child environment on Windows ([claude-code#90074](https://github.com/anthropics/claude-code/issues/90074)), so a bare inherited variable is not reliably visible to the server anyway.

Decision: the Claude manifest forwards the variable with `"env": { "DESIGN_PLAYBOOK_RUN_ROOT": "${DESIGN_PLAYBOOK_RUN_ROOT:-}" }`. Claude Code resolves `${…}` from its **own** (unsanitized) environment and injects the value explicitly, so the passthrough works on every platform; when unset it expands to `""`, which `server._run_root()` treats as unset and falls back to process cwd. The Issue 05 invariant holds — no *static* root is pinned. `env_vars` no longer appears in the Claude manifest.

Consequences:
- `tests/test_mcp_manifests.py` pins the split: Claude asserts no `env_vars` + an `${…}` `env` interpolation; Codex still asserts `env_vars`. The shared "no static run root" check now allows an interpolation value and rejects only static literals.
- `.mcp.json` is hand-maintained (not generated); the `validate.py` / `doctor.py` bundled-MCP gates check server presence + `${CLAUDE_PLUGIN_ROOT}` only, and `package_inventory` reads `args`, so none are affected by the env-channel change.
- The reliable, cross-platform run-root channel remains the per-call `run_root` argument to `execute_capture_plan`; the env forward is a convenience for a globally configured root.
