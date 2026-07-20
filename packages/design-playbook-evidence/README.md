# design-playbook-evidence

Optional **Evidence Provider MCP adapter** for [design-playbook](../design-playbook/).

**v0.3+:** runtime is bundled inside the main plugin at
`packages/design-playbook/mcp/evidence/` and auto-registered via the plugin's
`.mcp.json` (`${CLAUDE_PLUGIN_ROOT}`). This sibling directory is a
**compatibility launcher + docs** surface for monorepo / older local configs.

Orchestrator still probes MCP `tools/list` for tool name `execute_capture_plan`; if
absent, step 8 falls back to manual provider or free-text `observed` (no G6).

## Tool

`execute_capture_plan`

| Field | Required | Notes |
| --- | --- | --- |
| `url` | yes | Target host URL (`http(s)://` or `file://`) |
| `type` | yes | `screenshot` \| `a11y tree` \| `interaction trace` |
| `state` | yes | Expected page state label (error/loading/ok/…) |
| `actions` | no | Trigger sequence (`click` / `fill` / `wait_for_state` / …) |
| `artifact_path` | yes | Relative path under the configured run root |

Returns: `artifact`, `observed_state`, `result` (`captured` \| `failed`), `error`.

**Hard contracts**

- Provider **never** writes any case variant of `manifest.jsonl` (orchestrator binds).
- Provider accepts only Runtime Object fields; criterion refs and unknown fields are rejected.
- Provider rejects absolute paths, `..` traversal, and symlink escapes outside the run root.
- Capture ≠ judge: `result` is collect outcome, not pass/fail.

## Install / MCP config

Requires Python 3 + [Playwright](https://playwright.dev/python/) with Chromium.

```bash
pip install playwright
playwright install chromium
```

**Preferred (plugin install):** no manual config — marketplace / `--plugin-dir`
loads `packages/design-playbook/.mcp.json`.

**Monorepo / manual config:** the plugin's [`packages/design-playbook/.mcp.json`](../design-playbook/.mcp.json) is the source of truth (marketplace / `--plugin-dir` loads it automatically). For a monorepo dev checkout, see the repo-root `.mcp.json`; for Codex, see [`mcp.example.toml`](./mcp.example.toml) (it also shows the `DESIGN_PLAYBOOK_RUN_ROOT` env). The compatibility launcher at `packages/design-playbook-evidence/server.py` still works for older local configs but is not the preferred path.

## Implementation notes

- Run root: `DESIGN_PLAYBOOK_RUN_ROOT`; when omitted, the MCP process cwd is used.
- Stack: stdlib JSON-RPC framing + Playwright sync API for capture only.
- Framing: Content-Length and newline JSON (same dual mode as preview adapter).
- `observed_state` reads `body[data-state]` / `[data-state]` when present; otherwise it is `unknown` (the requested `state` is intent, not observation).
- Not a full browser MCP — single-tool surface for playbook probe only.
