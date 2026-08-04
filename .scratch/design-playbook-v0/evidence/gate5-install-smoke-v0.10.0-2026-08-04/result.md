# Gate 5 install smoke — v0.10.0

**Date:** 2026-08-04
**Host:** Windows 11 · Claude Code 2.1.220 · isolated `CLAUDE_CONFIG_DIR`
**Release source at smoke time:** public `main` and tag `v0.10.0` at `aed0e87`
**Public npm artifact:** `design-playbook@0.10.0`

## Procedure

1. Created an empty Claude config directory under the system temp directory.
2. Added the public GitHub marketplace through the documented explicit HTTPS URL; no `--plugin-dir` dev load.
3. Installed `design-playbook@design-playbook` at user scope inside the isolated config.
4. Checked installed inventory, ran `claude plugin validate --strict`, and called `initialize` + `tools/list` on both installed MCP servers through their shipped process-boundary tests.
5. Installed public npm package `design-playbook@0.10.0` into a clean consumer directory and checked its shipped inventory.

## Results

| Check | Result |
| --- | --- |
| isolated config starts with no marketplaces | PASS |
| documented public HTTPS marketplace add | PASS |
| public marketplace HEAD | PASS — `aed0e87` |
| plugin install | PASS |
| installed version / enabled | **0.10.0 / true** |
| on-disk model skills | **8** |
| on-disk slash commands | **4** — includes `run-review` |
| registered MCP servers | **2** — preview + evidence |
| installed plugin strict validation | PASS |
| Preview MCP initialize + `tools/list` | PASS — `preview_prototype` |
| Evidence MCP initialize + `tools/list` | PASS — `execute_capture_plan` |
| public npm install | PASS — **0.10.0**, 8 skills, 4 commands, 2 MCP servers |
| npm registry shasum | `b4b9b3b84bb22a0057d2a1d24499642deed3af69` |

Claude Code 2.1.220 reports the eight model skills and four slash commands together as 12 skill-like entries under `plugin details`; on-disk counts preserve the product's 8 + 4 distinction.

## Honest limits

Interactive `/help` inspection is not automatable from this isolated CLI run. `plugin details`, exact on-disk counts, strict validation, and live MCP handshakes cover the component inventory.

## Verdict

**v0.10.0 public release-artifact install smoke PASS.** Public `main`, tag, GitHub Release, and npm resolve version 0.10.0 with the expected 8-skill / 4-command / 2-MCP installable surface.
