# preview* operating detail

Load only when `preview_prototype` is available (see [`load-map.md`](load-map.md)).

1. Generate disposable prototype HTML under `.scratch/<run>/preview/round-{n}.html`.
2. Call `preview_prototype` with path/html, summary, round, report_ref, options.
3. Require feedback floor (ADR-0008): non-empty feedback or anchors with selector+comment.
4. Confirm record must have `confirmed=true` and `floor_pass=true` before Fill.
5. Same blocker two repair rounds without new evidence → stop and report.

Skip narration template: `-> preview*: adapter absent, skipped (G5 not triggered; enable via packages/design-playbook/mcp/preview/ or host MCP)`.
