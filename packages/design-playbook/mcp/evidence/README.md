# Evidence MCP adapter (`execute_capture_plan`)

Runtime for the optional **observe\*** step. Writes capture artifacts only — **never** `manifest.jsonl`, never judges L6.

## `DESIGN_PLAYBOOK_RUN_ROOT`

| Setting | Meaning |
| --- | --- |
| Unset | Artifact paths resolve under the **MCP process cwd** |
| `"."` (default in package `.mcp.json`) | Same — relative to process cwd, **not** the chat workspace root |
| Absolute path | Preferred for cross-repo dogfood: set to the run root (e.g. `D:/…/nmg_bup_h5/.scratch/playbook-smoke/<run>`) so `evidence/L6.*.png` lands next to `manifest.jsonl` |

Relative values are resolved with `Path(value).resolve()` at process start semantics (cwd-relative). If captures appear under the plugin monorepo instead of the host run, check cwd and this env — the tool also returns **`written_path`** (absolute) so mis-roots are obvious without a filesystem search.

Example (host run):

```json
"env": {
  "DESIGN_PLAYBOOK_RUN_ROOT": "D:/code_space/app/.scratch/my-run"
}
```

Plugin auto-load: [`../.mcp.json`](../.mcp.json) (under `packages/design-playbook/`).  
Codex / manual: sibling [`mcp.example.toml`](../../../design-playbook-evidence/mcp.example.toml).

## Return shape

`artifact` (run-root-relative) · `observed_state` (from page `data-state`, else `unknown`) · `result` · `error` · **`written_path`** (absolute).

Orchestrator bind rules (verbatim `observed_state`, per-capture append, mirror surface notes): `skills/design-playbook/SKILL.md` step 8.
