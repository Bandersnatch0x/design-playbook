# design-playbook for Codex

## Install

**Preferred (Claude Code marketplace / plugin-dir):** install the main package
only. Preview + Evidence MCP servers are registered from
`packages/design-playbook/.mcp.json` using `${CLAUDE_PLUGIN_ROOT}`.

**Codex skills (cross-platform Python helper):**

```bash
# from repo root — copies/symlinks skill trees into ~/.codex/skills
python packages/design-playbook/codex/install_skills.py
# or manual:
#   ln -s <abs>/packages/design-playbook/skills/design-playbook ~/.codex/skills/design-playbook
#   (repeat for ux-spec, ui-picker, craft-guard, native-craft, ui-evaluator)
```

Or `@` reference a single skill:

```text
@packages/design-playbook/skills/design-playbook/SKILL.md
```

**MCP (optional but recommended for G5/G6):**

```toml
# ~/.codex/config.toml — use plugin-bundled runtimes
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
2. Standard order: `ux-spec` → `ui-picker` → `fill` → `craft-guard` → `ui-evaluator`.

Native desktop order: `ux-spec` → `native-craft` → `ui-picker` → `fill` → `craft-guard` → `ui-evaluator`.

Run `native-craft` only for an explicit native-desktop/native-feel target. Web and mobile Web skip `native-craft`; if the platform is unclear, ask before choosing the order. The orchestrator owns the decision gate, render-surface seam handoff, and fail-closed behavior.

Mirror the orchestrator's skip narration (SKILL.md Steps preamble): when a step is skipped, output one line — step name + reason + how to enable, with the gate label when one applies, e.g. `-> preview*: adapter absent, skipped (G5 not triggered; enable via packages/design-playbook/mcp/preview/ or host MCP)`.

## Compose

- Style DB → ui-ux-pro-max
- Visual risk → frontend-design
- Pipeline + acceptance → design-playbook
