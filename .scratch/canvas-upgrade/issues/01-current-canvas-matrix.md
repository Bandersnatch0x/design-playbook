# Ticket 01-current-canvas-matrix — 当前画布能力矩阵

Type: research
Status: resolved
Resolved: 2026-08-07

## Question

把 `packages/design-playbook/mcp/preview/`（含 `control.html` / `control.js` / `control.css` + 任何相关 server / transport / round 文件）以及它运行时所处的页面（preview MCP 渲染的原型页面）的实际能力，列成一份 capability matrix，作为后续 gap 分析的当前基线。Matrix 至少要覆盖：

- **交互维度**：选择（pin / 锚点）、批注（comment / feedback）、编辑（drag / resize / recolor / 文本）、拖拽、框选、多选、撤销 / 重做。
- **渲染能力**：DOM 现状、是否支持 iframe / 跨源、视觉缩放、画布坐标系。
- **状态维度**：持久化（表单 POST → server / 无）、轮次（`round-N.html`）、history、撤销 / 重做、状态恢复。
- **版本 / 历史能力**：是否存历史快照、是否有 diff、是否有命名版本、是否有分支。
- **协作能力**：单端 vs. 多端、是否有冲突合并 UI。
- **可访问性 / 移动端**：键盘可达、屏幕阅读器、`@media (max-width: 720px)` 行为。
- **外部契约**：上游协议（`preview_prototype` MCP）、下游消费（`/decide` 提交）、不变量（G5 confirm 门）。
- **已知 trade-off / 痛点**：从仓库文件注释（`control.js` 里的 `I1` / `I2` / `I4` / `I8` / `I13` / `I18` / `P1.x` 等标签）和 ADR（0008 / 0013）抽取。

## 资产

产出 `.scratch/canvas-upgrade/assets/current-canvas-matrix.md`（行 = 能力，列 = 当前实现 / 备注 / 来源文件:行号）。

## Answer

矩阵已产出：8 个维度、约 46 个能力项，全部附 `文件:行号`（基于对 control.{html,js,css}、browser/transaction/server/control.py、i18n.py、util.py、_transport.py、ADR-0008/0013、design-playbook-preview README、g5 fixtures 与 showcase preview 的实读）。关键发现：① 现有 surface 是 G5 人工确认门的批注覆盖层，非可视化编辑器——交互仅 pin 选择 + 批注文本，无拖拽/框选/多选/undo；② 渲染为"受信任 parent 页 + sandboxed iframe（无 allow-same-origin）"双 DOM，G5 信任边界带来连锁成本（postMessage 桥、双份 cssPath、跨源 anchor el=null 的 label 退化）；③ 状态/版本极薄——客户端内存零持久化，服务端仅"原子 JSON 决策 entry + round 文件 + 哈希"，无 diff/分支/命名版本，单端 fail-closed，与 Figma/Stitch 目标差距最大的正是版本与协作维度。资产路径：`.scratch/canvas-upgrade/assets/current-canvas-matrix.md`。

## 来源

- `packages/design-playbook/mcp/preview/control.html`
- `packages/design-playbook/mcp/preview/control.js`
- `packages/design-playbook/mcp/preview/control.css`
- `packages/design-playbook-preview/`（compatibility launcher，定义协议面）
- `docs/adr/0008-preview-feedback-floor.md`
- `docs/adr/0013-preview-decision-transaction.md`
- 任何与 round / decide / transport 相关的 python 文件

## 约束

- 只读，不改产品代码。
- 不引用未直接读过的源文件。
- 行号必须精确（验证后写入）。
- matrix 与 issue-tracker markdown 约定一致（不写进 SSOT references/，仅作为 effort 内部资产）。