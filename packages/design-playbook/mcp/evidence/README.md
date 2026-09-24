# Evidence MCP adapter (`execute_capture_plan`)

Runtime for the optional **observe\*** step. Writes capture artifacts only — **never** `manifest.jsonl`, never judges L6.

## `DESIGN_PLAYBOOK_RUN_ROOT`

| Setting | Meaning |
| --- | --- |
| Unset | Artifact paths resolve under the **MCP process cwd** (the packaged `.mcp.json` passes the variable through, it does not pin a value) |
| `"."` (a host config that pins it) | Same — relative to process cwd, **not** the chat workspace root |
| Absolute path | Preferred for cross-repo dogfood: set to the run root (e.g. `/path/to/host-app/.scratch/playbook-smoke/<run>`) so `evidence/L6.*.png` lands next to `manifest.jsonl` |

Relative values are resolved with `Path(value).resolve()` at process start semantics (cwd-relative). If captures appear under the plugin monorepo instead of the host run, check cwd and this env — the tool also returns **`written_path`** (absolute) plus a `warnings` entry so mis-roots are obvious without a filesystem search.

**Cannot restart the server (`--plugin-dir` dev load)?** Pass `run_root` on the tool call — an absolute `.scratch/<run>/` that already carries a run marker (`plan.md` / `point-back.md`). Resolution order is `run_root` → `DESIGN_PLAYBOOK_RUN_ROOT` → process cwd, and the argument binds only that one call, so a mistyped or markerless root fails the capture instead of scattering evidence.

## What each capture type writes

| `type` | Bytes | Name it |
| --- | --- | --- |
| `screenshot` | PNG (plus a `<stem>.probe.json` sidecar when the adapter can probe) | `evidence/<leaf>.png` |
| `a11y tree` | JSON envelope `{"format": "aria_snapshot", "tree": "…"}` — `tree` is Playwright's indentation text, not a node/role tree | `evidence/<leaf>.json` |
| `interaction trace` | Playwright trace **ZIP** (actions + snapshots inside) | `evidence/<leaf>.trace.zip` — the Provider refuses a non-`.zip` name |

Example (host run):

```json
"env": {
  "DESIGN_PLAYBOOK_RUN_ROOT": "/path/to/app/.scratch/my-run"
}
```

Plugin auto-load: [`../.mcp.json`](../.mcp.json) (under `packages/design-playbook/`).  
Codex / manual: sibling [`mcp.example.toml`](../../../design-playbook-evidence/mcp.example.toml).

## Return shape

`artifact` (run-root-relative) · `observed_state` (from page `data-state`, else `unknown`) · `result` · `error` · **`written_path`** (absolute).

Orchestrator bind rules (verbatim `observed_state`, per-capture append, mirror surface notes): `skills/design-playbook/SKILL.md` step 8.

## Mirror pages and `data-state`

When capture uses a semantic mirror (not the live Fill host), set a root marker the provider can read:

```html
<body data-state="error">…</body>
```

`observed_state` comes only from that probe (else `unknown`). Do not overwrite it in the manifest with the request's `state` field.
