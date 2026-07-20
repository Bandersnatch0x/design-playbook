# ADR-0009: Bundled MCP adapters inside the plugin package

## Status

Accepted (2026-07-20). Supersedes the *distribution* aspect of the ADR-0005 sibling split for the two MCP adapters; the sibling directories remain as compatibility launchers.

## Context

ADR-0005 split preview/evidence into optional sibling packages so the plugin package stayed a clean redistributable root. In practice that made install two-step: the plugin installs via the marketplace, but each adapter still needed a hand-written host MCP entry pointing into the repo — the "ghost dependency" cold-start pain (dx-feedback ③). Claude Code plugins support a plugin-root `.mcp.json` whose servers launch via `${CLAUDE_PLUGIN_ROOT}`, which the split layout could not use.

## Decision

1. Adapter runtimes move into the plugin package: `packages/design-playbook/mcp/{preview,evidence}/`. Shipping **self-authored** Python runtime is within ADR-0003's authored-only scope (the ban is on third-party corpus content, not on our own code).
2. `packages/design-playbook/.claude-plugin/` stays plugin.json-only (ADR-0006). MCP servers are declared in the plugin-root `.mcp.json` via `${CLAUDE_PLUGIN_ROOT}/mcp/...`, so a marketplace install gets `preview*`/`observe*` with zero manual MCP config.
3. `packages/design-playbook-{preview,evidence}/server.py` remain as thin runpy **compatibility launchers** for existing local configs; their READMEs label them as such. No sunset milestone yet — policy is decided in the v0.3.1 cycle (wayfinder `.scratch/dedup-single-source/`, issue 05); actual removal is not a patch-release change.
4. Root `.mcp.json` (repo-dev convenience) points at the bundled paths.

## Consequences

- `scripts/validate.py` gains a bundled-MCP gate (`.mcp.json` shape, both servers present, `${CLAUDE_PLUGIN_ROOT}` usage, runtime files exist).
- CI syntax-checks and smoke-runs the bundled paths and keeps the launchers covered.
- ADR-0008 enforcement-site paths updated to `mcp/preview/`.
- The orchestrator's absent→skip contract is unchanged: bundling removes the manual-config step, not the optionality (hosts without MCP support still skip `preview*`/`observe*`).
- Launch config is intentionally present in three forms (plugin `.mcp.json` / root `.mcp.json` / `mcp.example.toml` for manual hosts); sibling README JSON blocks should become pointers if they drift.
