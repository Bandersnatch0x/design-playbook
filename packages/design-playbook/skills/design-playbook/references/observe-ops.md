# observe* operating detail

Load only when `execute_capture_plan` is available (see [`load-map.md`](load-map.md)).

1. Derive capture plan from each runtime L6 criterion (`Given/When` → state+actions).
2. Call capture contract v1: `schemaVersion: 1`, explicit `viewport`, default freeze on.
3. Bind per orchestrator step 9 / spec A1: one `manifest.jsonl` line per L6 criterion; `artifact` is the primary-proof leaf; `capture` holds the original call; `request` is the Provider contract echo.
4. Prefer live host URL; mirror surfaces require `surface: mirror` note + evaluator finding.
5. Screenshot sidecar, `WEB_VIEWPORTS` seed, `wait_for_state`, and `storage_state` — orchestrator step 9 (SSOT).

Skip narration template: `-> observe*: adapter absent, skipped (G6 not triggered; enable via packages/design-playbook/mcp/evidence/ + Playwright)`.
