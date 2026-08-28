<!-- generated-by design-playbook v0.21.0 -->
# design-playbook for Codex

## Install (path of record)

Marketplace catalog lives at the **repo root** (same GitHub repo as Claude Code).

```bash
# published
codex plugin marketplace add Bandersnatch0x/design-playbook
codex plugin add design-playbook@design-playbook

# local monorepo (dev)
codex plugin marketplace add <abs-path-to-repo-root>
codex plugin add design-playbook@design-playbook
```

Verify:

```bash
codex plugin list -m design-playbook --available --json
# expect: design-playbook@design-playbook, enabled=true after add
```

Codex-native manifest: `packages/design-playbook/.codex-plugin/plugin.json`  
Codex MCP (relative paths, no `CLAUDE_PLUGIN_ROOT`): `.codex-plugin/mcp.json`  
Skills: `packages/design-playbook/skills/*`

## Fallback: skills-only install

If you only want skills under `~/.codex/skills` (no plugin marketplace):

```bash
# from repo root — copies/symlinks skill trees into ~/.codex/skills
python packages/design-playbook/codex/install_skills.py --force
# or @-reference a single skill:
#   @packages/design-playbook/skills/design-playbook/SKILL.md
```

Register MCP directly (fallback when `codex plugin add` is unavailable):

`codex plugin add` depends on a healthy codex marketplace subsystem. If `codex doctor`
or `codex plugin marketplace list` fails (e.g. a stale marketplace source path), register
the servers directly in `~/.codex/config.toml` (or your `CODEX_HOME`):

```toml
# ~/.codex/config.toml  (or $CODEX_HOME/config.toml)
[mcp_servers.design-playbook-preview]
command = "python"
args = ["<abs>/packages/design-playbook/mcp/preview/server.py"]

[mcp_servers.design-playbook-evidence]
command = "python"
args = ["<abs>/packages/design-playbook/mcp/evidence/server.py"]
# evidence also needs: pip install playwright && playwright install chromium
```

Verify: `codex mcp list` should list both. `preview*` needs a system Edge/Chrome (the
adapter spawns it via `--app=`); `observe*` needs Playwright + Chromium.

> **`preview*` silently skips when `preview_prototype` is absent.** If preview does not
> appear, the orchestrator probed `tools/list`, found no `preview_prototype`, and skipped
> G5 - this is designed skip behaviour, not a crash. Confirm the tool is registered
> (`codex mcp list`) before treating it as a preview failure. Codex end-to-end preview
> smoke is not yet validated (v0.4.4 deferred the codex E2E smoke; only evidence/G6 was
> server-level smoked).

## Load order

1. `skills/design-playbook/SKILL.md`
2. Standard order: `design-baseline?` → `ux-spec` → `ui-picker` → `fill` → `craft-guard` → `ui-evaluator`.

Native desktop order: `ux-spec` → `native-craft` → `ui-picker` → `fill` → `craft-guard` → `ui-evaluator`.

Conditional entry `design-baseline?` (ADR-0012) runs before `reference-intake?` when the router returns `requires_baseline`. Existing-product Fill requires a valid existing baseline, an accepted generated baseline, or an explicit user waiver.

Conditional entry `reference-intake?` (screenshot/URL/design/product analogy, ADR-0011) runs **before** `ux-spec?` when the router returns `requires_reference_contract` — fixed orchestrator order, not reorderable. Run `native-craft` only for an explicit native-desktop/native-feel target. Web and mobile Web skip `native-craft`; if the platform is unclear, ask before choosing the order. The orchestrator owns the decision gate, render-surface seam handoff, and fail-closed behavior.

Mirror the orchestrator's skip narration (SKILL.md Steps preamble): when a step is skipped, output one line — step name + reason + how to enable, with the gate label when one applies, e.g. `-> preview*: adapter absent, skipped (G5 not triggered; enable via packages/design-playbook/mcp/preview/ or host MCP)`.

Audit preferences (ADR-0033) apply identically on Codex. Follow `skills/design-playbook/SKILL.md` § *Audit preferences* as sole authority; this bridge adds no host-specific preference rules.

## Compose

- Style DB → ui-ux-pro-max
- Visual risk → frontend-design
- Pipeline + acceptance → design-playbook
