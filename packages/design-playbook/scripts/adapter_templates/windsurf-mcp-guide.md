# design-playbook MCP setup for Windsurf

Windsurf uses a **global** MCP config at `~/.codeium/windsurf/mcp_config.json`.
The generator never writes that file (ADR-0042 §4). Add the following entries
manually, replacing `<preview_path>` and `<evidence_path>` with the absolute
paths from your installed design-playbook package.

## Where are the server files?

```bash
# If installed via npm in a project:
node -e "console.log(require.resolve('design-playbook/mcp/preview/server.py').replace(/\\/mcp\\/.*/, ''))"

# If running from the design-playbook source repo:
# packages/design-playbook/mcp/preview/server.py
# packages/design-playbook/mcp/evidence/server.py
```

## ~/.codeium/windsurf/mcp_config.json snippet

```json
{
  "mcpServers": {
    "design-playbook-preview": {
      "command": "python",
      "args": ["<preview_path>"],
      "timeout": 3600000
    },
    "design-playbook-evidence": {
      "command": "python",
      "args": ["<evidence_path>"],
      "env": {
        "DESIGN_PLAYBOOK_RUN_ROOT": "<your-project-root>"
      },
      "timeout": 3600000
    }
  }
}
```

**design-playbook-preview** requires a system Edge or Chrome browser.  
**design-playbook-evidence** requires `pip install playwright && playwright install chromium`.

Both servers implement the absent→skip contract: the orchestrator probes each
tool at session start and skips the gate if the server is absent — no crash.
