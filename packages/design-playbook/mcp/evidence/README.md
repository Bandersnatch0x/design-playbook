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

Plugin auto-load: [`packages/design-playbook/.mcp.json`](https://github.com/Bandersnatch0x/design-playbook/blob/main/packages/design-playbook/.mcp.json)
(a repository file, not shipped in the npm tarball).
Codex / manual: sibling [`mcp.example.toml`](https://github.com/Bandersnatch0x/design-playbook/blob/main/packages/design-playbook-evidence/mcp.example.toml).

## Return shape

`artifact` (run-root-relative) · `observed_state` (from page `data-state`, else `unknown`) · `result` · `error` · **`written_path`** (absolute).

Orchestrator bind rules (verbatim `observed_state`, per-capture append, mirror surface notes): `skills/design-playbook/SKILL.md` step 8.

## Declared design binding (`design`)

An optional `design` object binds one capture to the token scales the page claims to use, so the screenshot probe can compare **rendered** computed values against the declaration instead of only reading source:

```json
"design": {
  "fontSizes": [14, 16, 20, 24],
  "colors": ["#f5f5f5", "#ffffff", "#1a1a1a", "#0b6bcb"],
  "radii": [4, 8, 12, 20]
}
```

- The binding is the **caller's declaration**. The runtime does not search for a design source, read any path, or fetch a URL, and it does not claim the declaration was user-confirmed.
- Axes are `fontSizes`, `radii` (finite px numbers or `"16px"` strings) and `colors` (opaque hex or `rgb()` literals), each an **array** of literals. A numeric literal must be a complete CSS `<number>` (`[+-]?digits[.digits][e±digits]`, ASCII digits only): `1_6px`, full-width digits, `16 px` and `inf` are not CSS numbers even though Python's `float()` reads them. Only CSS whitespace (space, tab, LF, CR, form-feed) is trimmed — NBSP and vertical tab stay inside the token, so such a literal is `undecidable` rather than quietly normalized. There is no second declaration shape: a scalar axis, a name→literal object and an explicit `null` are rejected at the contract boundary before the browser starts.
- A literal is only comparable when the browser paints it as written: `NaN`/`Infinity`/overflowing px values, non-CSS spellings, and translucent colours (`rgba(..., 0.5)`, `rgb(... / 10%)`) are named `undecidable` rather than silently dropped or read as their opaque channels. A fractional RGB channel is compared with the browser's own serialization (nearest integer, ties up: `12.5` paints `13`), never with a different rounding.
- The declaration is validated at the contract boundary and then travels into the capture result's `request` and the manifest request snapshot, so the manifest alone records what the probe was bound to.
- **Omit the key and the declared comparisons are undecidable, not clean**: the probes still run. The distinct computed font sizes come back as facts, the declared type-scale, palette and radius-scale comparisons cannot run and are named `undecidable`, while the declaration-independent concentric-radius relations are still measured (they need no scale, so an unbound capture can still carry radius `findings`). An empty finding list is never conformance on its own; omitting one axis leaves that axis undecidable too.
- Token references and relative units (`var(--x)`, `1rem`) are **not** resolved by the boundary — an unreadable *literal inside an array* is the probe's finding to report as `undecidable`, never dropped and never silently clean. The boundary only rejects a malformed *declaration*; it does not pretend to resolve token semantics.
- A malformed `design` (not an object, an unknown axis, a scalar/object/null axis) fails the capture closed at the contract boundary — it is an `error`, not a silent unbound capture.

The sidecar gains a `renderTokens` face (`findings` / `undecidable` / `distinctFontSizes` / `measurement_status` / `measurement_error`) plus the `design` it ran against, which is **absent** (not `null`) when unbound. Read `renderTokens.measurement_status` and `undecidable` before interpreting `findings`.

## Capture providers

The tool declaration carries `outputSchema` (`capture_contract.capture_result_schema`)
and behavior annotations, and the manifest line has a versioned schema
(`evidence/manifest_v1.schema.json`, read through `evidence/manifest_schema.py`).

A third-party capture tool implements `evidence/provider.py`'s `CaptureProvider` —
`tool_name`, `describe()` returning its tool declaration, `capture(arguments)`
returning the advertised payload — and calls `register_capture_provider(provider)`
before the adapter starts. The bundled provider is the default, so an
unregistered process behaves exactly as before; name-based discovery
(`probe_capture_provider`) still works.

The `design` binding narrows that compatibility promise, and it never makes a
bound capture look unbound:

- **Unbound calls** (no `design` key) are unaffected. An adapter written before
  T-155 receives the same arguments and keyword names as before, and its
  sidecar reports `renderTokens.measurement_status: unmeasured`.
- **Bound calls** carry `design` inside `arguments`. A provider that does not
  implement the render-token face leaves `render_tokens` absent, so the sidecar
  reports `renderTokens.measurement_status: unmeasured` — read it as blocked,
  never as a clean pass. An in-process adapter whose `capture_and_probe`
  predates the keyword fails the capture closed: the `TypeError` surfaces as
  `result: failed` with no sidecar, and no artifact is silently captured
  unbound.

## Mirror pages and `data-state`

When capture uses a semantic mirror (not the live Fill host), set a root marker the provider can read:

```html
<body data-state="error">…</body>
```

`observed_state` comes only from that probe (else `unknown`). Do not overwrite it in the manifest with the request's `state` field.
