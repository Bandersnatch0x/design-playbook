# Optional operations load map

| Reference | Load when | Gate if skipped |
| --- | --- | --- |
| [`preview-ops.md`](preview-ops.md) | MCP `tools/list` exposes `preview_prototype` after decision report | G5 not triggered; narrate enable path `mcp/preview/` |
| [`observe-ops.md`](observe-ops.md) | MCP `tools/list` exposes `execute_capture_plan` after craft | G6 not triggered; narrate enable path `mcp/evidence/` + Playwright |

Main orchestrator keeps routing, gates, boundaries, and Done-when criteria. Optional operating detail lives only in these references.
