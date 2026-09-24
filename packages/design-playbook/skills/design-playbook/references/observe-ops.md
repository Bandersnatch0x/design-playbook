# observe* operating detail

Load only when `execute_capture_plan` is available (see [`load-map.md`](load-map.md)).

1. Derive capture plan from each runtime L6 criterion (`Given/When` → state+actions).
2. Call capture contract v1: `schemaVersion: 1`, explicit `viewport`, default freeze on.
3. Bind per orchestrator step 9 / spec A1 with `python scripts/evidence_manifest.py append .scratch/<run>/ --criterion L6.<n> --artifact <name> --request '<json>'` — never hand-write binding helpers. One `manifest.jsonl` line per L6 criterion; `artifact` is the primary-proof leaf — a **bare filename relative to the run's `evidence/`** (no directory parts); `criterion` must equal the spec's `L6.<n>` exactly; `--request` is the capture result's `request` field verbatim (Provider contract echo; G6 requires it — the CLI refuses rows that would fail G6); optional `--capture '<json>'` holds the original call, `--source` a provenance note. Machine check right after binding: `python scripts/g6_evidence.py .scratch/<run>/point-back.md`.
4. Prefer live host URL; mirror surfaces require `surface: mirror` note + evaluator finding.
5. Screenshot sidecar, `WEB_VIEWPORTS` seed, `wait_for_state`, and `storage_state` — orchestrator step 9 (SSOT). P2/P3 observe* blocking findings get a stable `id` from ui-evaluator; `capture.storage_state` keeps the relative path only.
6. Artifacts belong under `.scratch/<run>/evidence/`. When a capture's `written_path` lands outside the run tree (provider run root resolved to a markerless cwd — the payload carries a `warnings` entry), recapture with `run_root: "<abs .scratch/<run>/"` on the same tool call; the argument binds the run root for that call only, so no MCP restart is needed. Move a stray file into the run's `evidence/` only when recapturing is impossible.
7. Artifact names state what the bytes are (Provider-enforced): an interaction trace is a Playwright trace **ZIP** — name it `<something>.trace.zip`, unzip to inspect, never read as text; an `a11y tree` is a JSON envelope `{"format","tree"}` whose `tree` is Playwright `aria_snapshot` indentation text (`.json`).

Skip narration template: `-> observe*: adapter absent, skipped (G6 not triggered; enable via packages/design-playbook/mcp/evidence/ + Playwright)`.
