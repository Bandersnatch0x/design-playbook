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

Manual MCP (only if not using `codex plugin add`):

```toml
# ~/.codex/config.toml
[mcp_servers.design-playbook-preview]
command = "python"
args = ["<abs>/packages/design-playbook/mcp/preview/server.py"]

[mcp_servers.design-playbook-evidence]
command = "python"
args = ["<abs>/packages/design-playbook/mcp/evidence/server.py"]
# evidence also needs: pip install playwright && playwright install chromium
```

## Load order

1. `skills/design-playbook/SKILL.md`
2. Standard order: `design-baseline?` → `ux-spec` → `ui-picker` → `fill` → `craft-guard` → `ui-evaluator`.

Native desktop order: `ux-spec` → `native-craft` → `ui-picker` → `fill` → `craft-guard` → `ui-evaluator`.

Conditional entry `reference-intake?` (screenshot/URL/design/product analogy, ADR-0011) runs **before** `ux-spec?` when reference materials are present — fixed orchestrator order, not reorderable. Run `native-craft` only for an explicit native-desktop/native-feel target. Web and mobile Web skip `native-craft`; if the platform is unclear, ask before choosing the order. The orchestrator owns the decision gate, render-surface seam handoff, and fail-closed behavior.

Conditional entry `design-baseline?` (ADR-0012) runs before `reference-intake?` for UI builds/fixes in repositories with meaningful existing first-party UI. Existing-product Fill requires a valid existing baseline, an accepted generated baseline, or an explicit user waiver.

Mirror the orchestrator's skip narration (SKILL.md Steps preamble): when a step is skipped, output one line — step name + reason + how to enable, with the gate label when one applies, e.g. `-> preview*: adapter absent, skipped (G5 not triggered; enable via packages/design-playbook/mcp/preview/ or host MCP)`.

## Compose

- Style DB → ui-ux-pro-max
- Visual risk → frontend-design
- Pipeline + acceptance → design-playbook
