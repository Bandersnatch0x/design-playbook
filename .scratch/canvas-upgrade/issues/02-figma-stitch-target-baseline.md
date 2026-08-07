# Ticket 02-figma-stitch-target-baseline — Figma/Stitch 目标能力基线

Type: research
Status: resolved
Resolved: 2026-08-07

## Question

沉淀一份"Figma/Stitch 级别画布"指什么的能力清单，作为后续 gap 分析的目标基线。澄清：用户口中的"Figma / Stitch 级别"是模糊词，必须先落到具体能力集合（不是照搬 Figma 全集，是抽出"使其成为 Figma/Stitch 级别"的最小能力子集 + 可选增强子集）。

矩阵至少覆盖：

- **核心层（缺一就称不上"级别"）**：可视化编辑（点选 / 拖拽 / resize / recolor / 文本编辑）、图层面板、组件与实例、自动布局、画框（frame / page）、设计令牌（variables / styles）。
- **结构层（强信号）**：命名版本（snapshot 历史）、分支与合并、Figma-style AST（节点树 / 引用图）、dev handoff（导出 CSS / Tailwind / JSON）、组件 props / variants。
- **扩展层（加分）**：实时协作、评论与定位、插件 API、原型交互（prototype flows）、智能布局、约束（constraints）、导出格式（Figma JSON / SVG / PNG）。
- **每个能力附**：Figma / Stitch 的对应名称（一手）、本 effort 是否需要（必须 / 可选 / 不要）、来源（外参链接 + 截图 / 二手描述）。

## 资产

产出 `.scratch/canvas-upgrade/assets/figma-stitch-target-baseline.md`（能力 × 来源 × 是否纳入目标）。

## 来源

- Figma 官方文档（核心层命名）：figma.com / help center / developer docs（核心与结构层）
- Stitch（Google Stitch / Galileo）：产品页 + 公开发布（最新动态，2026）
- 二手对照：design tools review / 类比文章（仅作名词核验，不作能力定义）
- 仓库内既有 SSOT（`packages/design-playbook/skills/*/references/*` 中关于组件 / 模板 / 设计的定义）— 看是否已经隐含某些能力

## 约束

- 只用一手 + 二手核验，不臆造能力。
- 区分"必须达到该级别"vs."达到该级别可选增强"——核心层 vs. 结构层 vs. 扩展层。
- 不绑定具体技术栈（Vue / React / Canvas / SVG / WebGL）；只列能力与目的，技术选型留给后续架构 ticket。
- 能力命名以 Figma / Stitch 公开词典为准，避免发明词（防术语漂移）。

## Answer

基线已沉淀为资产 `assets/figma-stitch-target-baseline.md`：核心层 6 项（可视化编辑、图层面板、组件与实例、自动布局、画框与页面、设计令牌）、结构层 5 项（命名版本、分支与合并、文档 AST、dev handoff、组件 props/variants）、扩展层 7 项（实时协作、评论、插件 API、原型、智能布局、约束、导出格式），必须项共 11 项。核心层最关键 5 项：C1 可视化编辑（当前 floating 批注层的最大缺口）、C2 图层面板、C4 自动布局、C6 设计令牌（直接对齐 SSOT design.md 的 `var(--*)`）、S3 文档 AST（本地版本控制的序列化底座）。Stitch 确认是 **Google Stitch**（stitch.withgoogle.com，前 Galileo AI，2026-03 "vibe design" 无限画布改版；一手来源为 blog.google 官方博文）；它偏 AI 生成优先，无公开图层面板/版本历史，故基线以 Figma 词典为主干、Stitch 补充 DESIGN.md 与原型语义。所有能力均带一手链接。