# Ticket 01-surface — 落点：指引住在哪个表面

Type: decision
Status: resolved
Resolved: 2026-08-03 (roundtable `.scratch/v0.10-run-review/roundtable-synthesis.md`)

纯 (a)：新增第四个 command `packages/design-playbook/commands/run-review.md`（内联 ~30 行），不新增 skill。否决扩 ui-review/ui-evaluator（单 run 语义不动，DX 最坚持项）；否决新 skill（gate 常量 + codex/AGENTS.md 编排污染，YAGNI/Arch）。orchestrator step 10 Done when 后加一行 pointer（cross-run, not a step of this run）。doctor GATE1 commands 3→4。
