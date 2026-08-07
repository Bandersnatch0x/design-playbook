# Figma/Stitch 目标能力基线

> Ticket 02 资产：把用户口中的"Figma/Stitch 级别画布"落到具体能力集合。
> 分层逻辑：**核心层** = 缺一就称不上该级别；**结构层** = 强信号（决定它是不是"正经设计工具"）；**扩展层** = 加分项。

## 方法学与来源

- **一手**（能力命名依据）：figma.com 官方 help center（help.figma.com）、Figma developer docs（developers.figma.com）、Google 官方博客（blog.google）、stitch.withgoogle.com。
- **二手**（仅名词核验，不作能力定义）：2026 年 3–8 月的独立评测/指南（wirelogs、o-mega.ai、aitoolsclub、nxcode、creativeainews）。
- 每项能力至少有 1 个一手链接；命名以 Figma/Stitch 公开词典为准，不发明词。

## Stitch 身份确认

- **结论：Google Stitch**（stitch.withgoogle.com）——Google Labs 的 AI-native 软件设计画布，前身 **Galileo AI**（2025-05 被 Google 收购，随 Google I/O 2025 发布；2026-03 "vibe design" 重大改版为无限画布）。
  - 一手：Google 官方博客《Introducing "vibe design" with Stitch》（https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/）；《Stitch's DESIGN.md format is now open-source》（https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-design-md/）。
- **歧义注明**：市场上另有其他命名含 "Stitch" 的产品（如 stitching 工具、lora 拼接等），但结合"Figma 级别画布"的语境、2026 年热度与"AI 生成 + 可编辑 + 导出代码"的语义，Google Stitch 是唯一合理指向。后续 gap 分析以 Google Stitch 为准。
- 特点：Stitch 是 **AI 生成优先**的工具（语言/草图/URL/语音 → UI），其画布能力偏向"生成 + 即时原型 + 导出"，**没有暴露** Figma 级别的图层面板、auto layout 编辑、版本历史等结构化能力（这些它靠"导出到 Figma 保留 Auto Layout + 可编辑图层"和 DESIGN.md 补齐）。因此本基线以 **Figma 词典为主干**，Stitch 只贡献 DESIGN.md（设计令牌）与"生成/原型"语义。

## 本地 SSOT 对齐（防术语漂移）

仓库 `packages/design-playbook/skills/*/references/*` 已隐含并可与本基线对齐的语义：

| SSOT 文件 | 已定义 | 对齐到本基线 |
| --- | --- | --- |
| `ui-picker/references/components.md` | 组件语义/来源、变体与状态（size/variant/loading/disabled）、组合边界 | 核心层 #3、结构层 #5 |
| `ui-picker/references/design.md` | 所有视觉值走 `var(--*)`、token 派生 hover/active/disabled | 核心层 #6（variables/design tokens） |
| `ui-picker/references/template.md` | 页面骨架声明（看板/列表/详情/设置） | 核心层 #5（frame/page）、结构层 #3（AST） |

即：本 effort 不必发明新术语，Figma variables ↔ `var(--*)`、components/variants ↔ SSOT 组件登记、frame/page ↔ template 骨架，直接映射。

---

## 核心层（缺一就称不上"Figma/Stitch 级别"）— 6 项

| # | 能力 | Figma 对应名 | Stitch 对应名 | 本 effort 需要 | 来源 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | 可视化编辑：点选 / 拖拽 / resize / recolor / 文本编辑（direct manipulation） | Select/Move 工具、properties panel（右栏调位置/尺寸/填充/文本） | Direct Edits（2026-03 起可直接改文本/换图/微调，不用重发 prompt） | **必须** | Figma: https://help.figma.com/editor/toolbar-tools/frame-tool（框架属性与画布操作）、https://help.figma.com/text（Figma Design 官方索引）；Stitch: https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/（AI-native canvas + iterate）；Direct Edits 见二手 https://o-mega.ai/articles/google-stitch-and-ai-design-tools-complete-guide | 当前画布是 floating 批注层，不是可编辑表面——这条是"可视化编辑器"的底线，也是本 effort 的核心缺口。 |
| C2 | 图层面板：层级树 / 选择 / 命名 / 显隐 / 锁定 / 排序 | Layers panel（左栏 File 标签；图层类型图标、嵌套展开、重命名、visibility/lock） | —（无独立 layers panel；对象即画布上的图层，导出 Figma 时保留可编辑图层结构） | **必须** | Figma: https://help.figma.com/hc/en-us/articles/360039831974（View layers and pages in the left sidebar）、https://help.figma.com/hc/articles/15297425105303（Explore design files: pages and layers）；Stitch: 二手 https://aitoolsclub.com/google-stitch-2-0...（导出 Figma 保留可编辑图层） | 层级树是文档 AST 的可见前端；无它则无法理解/导航文档。 |
| C3 | 组件与实例：可复用定义 + 引用 + 覆盖 | main component / instance / overrides / libraries | 生成组件（text/image/URL → UI 组件）；DESIGN.md 记录 component patterns | **必须** | Figma: https://help.figma.com/hc/en-us/articles/360038662654（Guide to components in Figma）；Stitch: https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-design-md/ | 直接对齐 SSOT `components.md`（组件语义/组合边界）。"实例"概念（instance ↔ main）是 Figma 级别核心，Stitch 未公开同等词。 |
| C4 | 自动布局：响应式容器（flow / padding / gap / 尺寸模式） | auto layout（vertical/horizontal/grid flow、padding、gap、hug contents / fill container / fixed / min-max） | 导出到 Figma 时保留 Auto Layout 与可编辑图层 | **必须** | Figma: https://help.figma.com/hc/en-us/articles/360040451373（Guide to auto layout）；Stitch: 二手 https://aitoolsclub.com/google-stitch-2-0... 与 https://www.nxcode.io/zh/resources/news/google-stitch-complete-guide-vibe-design-2026 | 无 auto layout 只有绝对定位的画布称不上该级别；这是"Figma 级别"的最小定义之一。 |
| C5 | 画框与页面：文档分块与组织（frame / page / section） | frames（top-level / nested / presets）、pages（每页独立 canvas）、sections | 无限画布上的 screens（ideation → prototype 单一工作区） | **必须** | Figma: https://help.figma.com/editor/toolbar-tools/frame-tool（frames）、https://help.figma.com/hc/articles/15297425105303（pages）；Stitch: https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/（infinite canvas） | 页面/画框是文档分块、导航与版本粒度的基础；对齐 SSOT `template.md` 页面骨架。 |
| C6 | 设计令牌：可复用值 + 别名 + 模式（variables / styles / tokens） | variables（collections / modes / alias，类型 color/number/string/boolean/timing/easing）、styles（color/text/effect/layout grid）、design tokens（primitive → semantic，W3C token 语义） | DESIGN.md（agent-friendly markdown，含颜色/字体/间距/组件规则；从 URL 提取设计系统；开源 spec） | **必须** | Figma: https://help.figma.com/hc/en-us/articles/15339657135383（Guide to variables in Figma）、https://www.figma.com/resource-library/design-tokens/；Stitch: https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-design-md/ | 直接对齐 SSOT `design.md` 的 `var(--*)` 强制。令牌是"设计系统级"画布与"图片编辑"的分水岭。 |

## 结构层（强信号 — 决定它是不是"正经设计工具"）— 5 项

| # | 能力 | Figma 对应名 | Stitch 对应名 | 本 effort 需要 | 来源 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | 命名版本历史（snapshot） | version history（autosave checkpoints + 手动命名版本、restore / duplicate / share link、非破坏性） | design agent 追踪项目整体历史并跨版本推理（未公开"命名版本"命名） | **必须** | Figma: https://help.figma.com/hc/en-us/articles/360038006754（View a file's version history）；Stitch: 二手 https://aitoolsclub.com/google-stitch-2-0... | 本 effort 主题之一（本地版本控制）。对应 map.md "命名快照 vs git 式 vs Figma 式"——S1 是三者共同底座。 |
| S2 | 分支与合并 | branching and merging（create branch / merge / request review / branch compare） | Agent Manager 并行探索多条方向、不丢进度（无 git 式 merge UI） | **可选** | Figma: https://help.figma.com/hc/en-us/articles/360063144053（version history 文内指向的 branching 条目）、https://help.figma.com/text（"Branching and merging / Guide to branching" 官方索引）；Stitch: 二手 https://o-mega.ai/articles/google-stitch-and-ai-design-tools-complete-guide | 强信号但非最低项；可先做线性命名快照，分支/合并留后续票。 |
| S3 | 文档 AST / 节点树 / 引用图（可序列化文档模型） | REST API：file 的 JSON 表示，每个 layer = node（node 树、组件/样式/变量端点、webhooks） | MCP server + SDK（外部工具可调 Stitch 能力） | **必须** | Figma: https://developers.figma.com/docs/rest-api/（files 端点返回 JSON node tree）；Stitch: https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/（Stitch MCP server and SDK） | 本地版本控制（diff/snapshot）必须有可序列化文档模型；S1 依赖 S3。 |
| S4 | Dev handoff：导出 CSS / Tailwind / JSON 等代码规格 | Dev Mode（inspect、codegen 多语言、Code Connect、Ready for dev 状态、compare changes、frame history） | HTML/CSS、React/JSX、Tailwind 导出；导出到 Figma（保留 Auto Layout） | **必须** | Figma: https://help.figma.com/hc/pl/articles/15023124644247-Guide-to-Dev-Mode；Stitch: 二手 https://o-mega.ai/articles/google-stitch-and-ai-design-tools-complete-guide（React/Tailwind/HTML-CSS 导出）与 https://aitoolsclub.com/google-stitch-2-0...（Figma 导出） | design-playbook 核心价值是设计→代码；preview 画布是反馈/锚点面，导出即 handoff。 |
| S5 | 组件 props / variants（组件参数化） | component properties（variants / boolean / instance swap / text）、variants 组织 | 生成组件含变体；DESIGN.md 组件规则 | **必须** | Figma: https://www.figma.com/best-practices/creating-and-organizing-variants/library-organization/（variants 最佳实践）、https://help.figma.com/hc/en-us/articles/5579474826519（Create and use component properties）；Stitch: https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-design-md/ | 与 SSOT `components.md`"变体与状态（size、variant、loading、disabled…）"一一对应。 |

## 扩展层（加分项）— 7 项

| # | 能力 | Figma 对应名 | Stitch 对应名 | 本 effort 需要 | 来源 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| E1 | 实时协作 | multiplayer tools、viewer history、cursor chat | collaboration（团队共享项目，二手） | **可选** | Figma: https://help.figma.com/text（"Multiplayer tools" 官方索引）；Stitch: 二手 https://www.creativeainews.com/blog/google-stitch-vibe-design-ai-ui | 插件内场景以单人为主；协作是产品级考量（对应 map.md 方向 C）。 |
| E2 | 评论与定位（锚点讨论） | comments（Guide to comments in Figma；REST comments 端点；comment on prototypes） | —（未确认公开评论功能） | **可选** | Figma: https://help.figma.com/text（"Comments" 官方索引）、https://developers.figma.com/docs/rest-api/（comments endpoints） | 当前画布已是批注层；是否升级为"评论线程 + 定位"待 gap 表定夺。 |
| E3 | 插件 API / 扩展接口 | Plugin API / widgets / REST API / webhooks | Stitch MCP server + SDK | **可选** | Figma: https://developers.figma.com/docs/rest-api/；Stitch: https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/ | 本 effort 内部接口优先，对外开放留后续。 |
| E4 | 原型交互（prototype flows） | prototyping（flows、connections、hotspots、triggers、actions、animations、overlays、smart animate、presentation view） | instant prototyping：把 screens "Stitch" 起来 + Play 预览；自动生成下一屏 | **可选** | Figma: https://help.figma.com/hc/en-us/articles/360040314193（Guide to prototyping in Figma）；Stitch: https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/（instant prototyping） | design-playbook 以静态验收为主；原型是加分。 |
| E5 | 智能布局 / 智能选择（辅助编排） | suggest auto layout、smart selection、smart animate | AI 生成布局 / 自动生成逻辑下一屏 | **可选** | Figma: https://help.figma.com/hc/en-us/articles/360040451373（suggest auto layout）与 https://help.figma.com/hc/en-us/articles/360040314193（smart animate）；Stitch: https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/ | 对本 effort 属于锦上添花。 |
| E6 | 约束（constraints） | constraints（child 随 parent resize 的响应属性） | —（无对应公开能力） | **不要** | Figma: https://help.figma.com/editor/toolbar-tools/frame-tool（frames 支持 constraints）、https://www.figma.com/best-practices/groups-versus-frames（约束语义） | Figma 旧式响应机制，已被 auto layout 取代；Stitch 不暴露；本 effort 不必单独实现。 |
| E7 | 导出格式（Figma JSON / SVG / PNG） | export static designs（SVG/PNG）、REST API images 端点、copy as code | 代码导出为主（HTML/CSS/React/Tailwind） | **可选** | Figma: https://help.figma.com/text（"Export static designs from Figma" 官方索引）、https://developers.figma.com/docs/rest-api/（Get images endpoint）；Stitch: 二手 https://o-mega.ai/articles/google-stitch-and-ai-design-tools-complete-guide | SVG/PNG 对 preview 反馈面有用；"Figma JSON" 为专有格式，不采用，用自有 AST JSON（S3）代替。 |

---

## 汇总

- **核心层 6 项**：C1 可视化编辑、C2 图层面板、C3 组件与实例、C4 自动布局、C5 画框与页面、C6 设计令牌。
- **结构层 5 项**：S1 命名版本、S2 分支与合并（可选）、S3 文档 AST、S4 dev handoff、S5 组件 props/variants。
- **扩展层 7 项**：E1 实时协作、E2 评论与定位、E3 插件 API、E4 原型交互、E5 智能布局、E6 约束（不要）、E7 导出格式。
- **必须项共 11 项**（C1–C6 + S1 + S3–S5），**可选 10 项**，**不要 1 项**（E6）。
- 后续 gap 分析即以"必须 11 项"为 baseline，对照 01 票的当前画布能力矩阵。
