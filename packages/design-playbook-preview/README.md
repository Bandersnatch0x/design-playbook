# design-playbook-preview

Optional **Preview MCP adapter** for [design-playbook](../design-playbook/).

**v0.3+:** runtime is bundled inside the main plugin at
`packages/design-playbook/mcp/preview/` and auto-registered via the plugin's
`.mcp.json` (`${CLAUDE_PLUGIN_ROOT}`). This sibling directory is a
**compatibility launcher + docs** surface for monorepo / older local configs.

Orchestrator still probes MCP `tools/list` for tool name `preview_prototype`; if
absent, preview is skipped and the pipeline goes straight to Fill.

## Tool

`preview_prototype`

| Field | Required | Notes |
| --- | --- | --- |
| `path` | one of path/html | Absolute HTML path (preferred) |
| `html` | one of path/html | Inline full-page HTML |
| `summary` | yes | Decision-report summary / change note |
| `round` | yes | 1-based loop index |
| `report_ref` | yes | Decision report path or version id |
| `options` | no | Default depends on locale (see i18n.py), e.g. `["确认通过","需要修改"]` (zh) or `["Confirm","Needs changes"]` (en) |

Returns: `confirmed`, `selected_options`, `feedback`, `anchors`, `round`,
`confirm_record_path`, `aborted`.

`anchors` is a list of `{selector, label, comment, tag}` from DOM pin comments
when the user enables **点选批注** and clicks elements before revise.

On confirm, writes `.scratch/<run>/preview/confirm-round-{n}.json` (next to the
prototype when `path` is under `preview/`) and appends `log.md`.

## Install / MCP config

Stdio server, stdlib only:

**Preferred (plugin install):** no manual config — marketplace / `--plugin-dir`
loads `packages/design-playbook/.mcp.json`.

**Monorepo / manual:**

```json
{
  "mcpServers": {
    "design-playbook-preview": {
      "command": "python",
      "args": ["<abs-path-to-repo>/packages/design-playbook/mcp/preview/server.py"]
    }
  }
}
```

Compatibility launcher (same process, redirects to the bundled runtime):

```json
{
  "mcpServers": {
    "design-playbook-preview": {
      "command": "python",
      "args": ["<abs-path-to-repo>/packages/design-playbook-preview/server.py"]
    }
  }
}
```

## Implementation notes

- Stack: pure Python 3 stdlib (JSON-RPC framing + local HTTP form + Chromium `--app` window).
- Window: centered app window (Chrome/Edge); falls back to default browser.
- On decide: the adapter-launched app window is hidden immediately, then its
  private Chromium process tree is terminated. A URL opened manually in an
  existing browser tab is outside adapter ownership and must be closed there.
- Revise UX: optional DOM pin mode → per-element comments in the dock.
- Not Tauri/wry — ticket 06 leaves stack open; this is the minimal usable surface.
- Prototype files must not be copied into Fill source trees (orchestrator rule).
