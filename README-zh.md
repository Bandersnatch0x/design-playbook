<div align="center">

<img src="packages/design-playbook/showcase/screenshots/hero.png" alt="design-playbook — 给 coding agent 的 Design I/O" width="100%" />

# 🎴 design-playbook

### *为 coding agent 提供带证据的 UI 交付闭环。*

[![Version](https://img.shields.io/badge/Version-0.25.0-2DD4BF?style=flat-square&logo=semver&logoColor=black)](https://www.npmjs.com/package/design-playbook)
[![License](https://img.shields.io/badge/License-MIT-2DD4BF?style=flat-square&logo=opensourceinitiative&logoColor=black)](./packages/design-playbook/LICENSE)
[![Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-2DD4BF?style=flat-square&logo=claude&logoColor=black)](#-试一把)
[![Skills](https://img.shields.io/badge/Skills-9-2DD4BF?style=flat-square)](#-skills-与命令)
[![Commands](https://img.shields.io/badge/Commands-8-2DD4BF?style=flat-square)](#-skills-与命令)
[![Codex](https://img.shields.io/badge/Codex-ready-2DD4BF?style=flat-square)](./packages/design-playbook/codex/AGENTS.md)

</div>

---

## ✅ 对照声明的判据和证据评审 UI

面向使用 coding agent 修改既有 Web UI 的前端或产品工程师，design-playbook 把需求、验收判据、证据与修复责任人串起来。必需证据缺失时，判据保持 `blocked`；显式跳过评审器时，产出 `audited: false` 骨架，而非已审计的 Pass。发现指回所属声明，阻塞性发现回流修复。评审器不替代具名人工角色的语义批准，也不保证独立判断。

承载它的是两个面：

1. **带证据的验收**——`ui-evaluator` + point-back 台账：发现必须引用绑定判据的证据，闭环轨迹是 run 的一部分，不是聊天摘要。
2. **存量产品的 UI 改动**——`design-baseline` 在改动既有产品之前先发现、校验或生成项目 `DESIGN.md`，让改动与已上线的部分保持一致。

### 当前阶段

截至 2026-09-24，项目处于**维护者自用与维护阶段**，catalog 提交和参与者招募均已暂停。
现有安装路径继续保留；内部 dogfood、历史案例和自动回放不构成外部采用或自愿复用证据。
新增能力 spec 只是提案，不代表实施或发布承诺。恢复活动须经维护者明确决定，
不因日期到达或内部测试通过而自动恢复。

## ⚡ 一条命令，三份产物

证据背后的机制是一条链路：

```text
/design-playbook:design-io <你的 UI 需求>
```

一次 Design I/O run 使用随包内置的 MCP 配置，在宿主支持且运行前提满足时，将三类核心产物记录在 `.scratch/<run>/`：

1. **`spec.md`**——六层的"什么是好"声明（意图 → 验收），写在任何 UI 之前
2. **决策报告**——骨架 + 组件语义，写在任何代码之前
3. **Point-back 台账**——每条验收发现都写明它违反的是哪条声明，外加闭环轨迹

## 🎬 试一把

**Claude Code**

```text
/plugin marketplace add https://github.com/Bandersnatch0x/design-playbook.git
/plugin install design-playbook@design-playbook
```

**Codex**

```bash
codex plugin marketplace add Bandersnatch0x/design-playbook
codex plugin add design-playbook@design-playbook
```

然后带命名空间调用（裸 `/design-io` 仅是 `--plugin-dir` 开发态别名）：

```text
/design-playbook:design-io <你的 UI 需求>
```

用 Cursor、Windsurf、Gemini CLI 等 30 个受支持的 agent？见 [🌐 跨平台安装](#-跨平台安装)。诚实降级：30 个里有 22 个走的是生成的 `AGENTS.md` 地板（编排契约 + MCP 安装指南，命令退化为提示文档）——每一档实际拿到什么，分层表写得明明白白。

Codex 安装细节、marketplace 不可用时的 `[mcp_servers.*]` 直配 fallback、preview 前置条件：见 [`packages/design-playbook/codex/AGENTS.md`](./packages/design-playbook/codex/AGENTS.md)。

**运行前提**：受支持的宿主已注册相应 MCP 工具，内置运行时需要 Python 3，Preview 需要本地浏览器。
运行取证还需要 Playwright 与 Chromium，以及可访问的应用、相应测试数据和登录态。见
[取证安装说明](./packages/design-playbook-evidence/README.md#install--mcp-config)。
可选适配器不可用时会披露限制，但跳过取证不等于必需证据已通过。

<details>
<summary>本地开发 / 自测</summary>

marketplace catalog 在**仓库根目录**（不在 package 内）：

```text
claude --plugin-dir <绝对路径>/packages/design-playbook      # 开发加载，免安装
/plugin marketplace add <仓库根绝对路径>                     # 本地 marketplace
/plugin install design-playbook@design-playbook

codex plugin marketplace add <仓库根绝对路径>
codex plugin add design-playbook@design-playbook
```

版本权威：`packages/design-playbook/package.json` 与
`packages/design-playbook/.claude-plugin/plugin.json` 保持版本一致；
桥接包、根 catalog、README 徽章和生成的 Codex 快照随之同步。

</details>

## 📸 证据，不是承诺

验收记录必须保留证据边界：

- **Point-back**——每个验收发现都点名拥有它的 spec、领域规则或工艺声明。不存在无主的"看起来不错"。
- **回流（recirculate）**——blocking 发现回流到 owning 阶段直到闭环；闭环轨迹本身就是 run 产物的一部分。
- **不能静默跳过**——跳过审计仍会产出 point-back 骨架，但标记 `audited: false`，strict 校验不把它当已审计结果放行。
- **缺失不等于不适用**：必需证据缺失为 `blocked`；`not-applicable` 必须有未触发的适用条件与理由，不能因为取证工具不可用就判不适用。

[历史案例与用户旅程](./packages/design-playbook/showcase/README.md#user-journey)：三次独立任务，外加一个[完整的当前实跑](./packages/design-playbook/showcase/case-reader/index.html)（案例阅读器）——规格、真实预览确认、Fill、工艺审计、运行取证、评审、静态交付全程打包，并附[跨 run 回顾报告](./packages/design-playbook/showcase/run-review-2026-09-08.md)。SwarSight 队列案例保留了规格、设计决策与评审修复记录，早于当前计划交接和运行取证要求。

下列图片是该历史案例的内容说明图，不是工作流执行的原始截屏：

| | |
| :---: | :---: |
| **1 · ux-spec**——写 UI 之前的六层 spec | **2 · ui-picker**——写代码之前的决策报告 |
| ![六层 spec](packages/design-playbook/showcase/screenshots/01-spec.png) | ![决策报告](packages/design-playbook/showcase/screenshots/02-decision-report.png) |
| **3 · ui-evaluator**——point-back + 回流闭环 | **历史结果**——六项案例检查，不是当前门禁矩阵 |
| ![Point-back 发现](packages/design-playbook/showcase/screenshots/03-point-back.png) | ![历史案例检查摘要](packages/design-playbook/showcase/screenshots/04-gates.png) |

**预览评审工作台**——检查设计、定位反馈，再确认或要求修改。[已收录的人工确认记录](./packages/design-playbook/showcase/README.md#case-b) 来自独立的入驻表单任务，不是队列案例的确认，也不代表产品实现已通过验收：

![Preview 确认工作台——批注后确认或打回](packages/design-playbook/showcase/screenshots/05-preview-confirm.png)

查看[三类案例及各自的证据边界](./packages/design-playbook/showcase/README.md)，或打开[完整的当前实跑](./packages/design-playbook/showcase/case-reader/index.html)——其中包含接续暂停点与生成的静态交付包。重试界面来自另一任务，使用本地模拟数据，不执行插件。

## 🔁 一条链路跑到底

先声明什么是好，再对着声明生成，最后对着同一份声明验收。每个 run 执行同一条可预测的 **Design I/O** 链路：

```text
design-baseline? → reference-intake? → ux-spec? → plan? → (native-craft?)
  → ui-picker → (preview*) → fill → craft-guard† → (observe*†) → ui-evaluator†
                              ▲                                       │
                              └────────────── recirculate ───────────┘
```

六个**声明**拥有"什么是好"（`spec` · `domain` · `craft` · `design` · `components` · `template`）；两个**契约**管工作怎么进链路（`skill` 管时机，`evaluator` 管验收 + 回流）。

<details>
<summary>标记图例（<code>?</code> / <code>*</code> / <code>†</code>）</summary>

| 标记 | 含义 |
| :--- | :--- |
| `?` | 条件入场——已有产品的 UI 修改先跑 `design-baseline?`；需求里带截图 / URL / 类比时再跑 `reference-intake?` |
| `*` | 适配器阶段——仅在其打包的 MCP 工具注册时运行；否则跳过，绝不硬报错 |
| `†` | 用户可选审计阶段（设计决策记录 [ADR-0033](./docs/adr/0033-audit-acceptance-user-preferences.md)）——首次运行问一次，选择记入 `.design-playbook/preferences.yaml`（版本化；本机覆盖写在 gitignore 的 `preferences.local.yaml`） |

</details>

## 🧩 Skills 与命令

包内九个 skill（`/design-playbook:<名>`）：

| Skill | 职责 |
| :--- | :--- |
| `design-playbook` | 🎯 编排（全链路；run-profile 档位定档 P1/P2/P3） |
| `design-baseline` | 🧭 初始化发现、校验或从已有 UI 生成项目 `DESIGN.md` 草稿 |
| `reference-intake` | 📎 参考契约（截图/URL/类比 → Keep/Change/Do not copy） |
| `ux-spec` | 📋 六层 spec 声明（S0-S6 成形会话：问题/假设/确认批次 + 会话工件） |
| `ui-picker` | 🧱 骨架 + 组件语义 + 设计决策条目（记录/对比/探索三档） |
| `craft-guard` | 🛡️ 细节工艺检查——间距、层级、动效等手作细节（反 AI 味），对照内置规则表 |
| `native-craft` | 🖥️ 桌面原生手感声明 |
| `ui-evaluator` | ✅ 验收——每个发现都指回它违反的声明，blocking 发现回流重修 |
| `component-distill` | 已有跨 run 组件/token 晋升提案，只出报告；持久晋升需用户裁决，不属于单 run 管线 |

**八个命令**：`design-io`（全链路）· `ux-spec`（只出 spec）· `ui-review`（只验收）· `run-review`（跨 run 复盘）· `run-status`（阶段与恢复叙述）· `run-handoff`（为已评审 run 出静态交付包）· `doctor`（安装面健康）· `component-distill`（跨 run 提案，不自动晋升）

## 🎚️ Run 档位（P1/P2/P3）

每个 run 在 `plan.md` **run-profile** 块声明档位——流程重量与变更后果成正比。**升档自动**（纠偏信号一出现即升档并补走新增环节），降档需用户。

<details>
<summary>档位矩阵</summary>

| 档 | 范围 | 门禁面 |
| :--- | :--- | :--- |
| **P1** 点修 | 单一 owning 层 point-back 修复，不触碰 decided 字段 | 注册表子集求值；R4/R5（+R2 行级）路由 |
| **P2** 标准 | 基线内功能变更（新判据、R/C 决策） | 适用谓词全求值；成形会话 + G9/G10 |
| **P3** 全量 | decided 字段修订（supersedes）、结构性重构、E 档决策 | G1-G12 全谱 + 采样矩阵完整执行 |

</details>

档位与重入决策见 [ADR-0029](./docs/adr/0029-vnext-closed-loop-final-state.md)。维护者说明见[中文文档入口](./docs/README.md)。

## 🔌 适配器（随主插件打包）

Preview / Evidence MCP 运行时已放进主插件（`packages/design-playbook/mcp/` +
带 `${CLAUDE_PLUGIN_ROOT}` 的 `.mcp.json`）。marketplace 安装即注册两个工具，
无需第二包；orchestrator 仍会**探测**，宿主无 MCP 工具时跳过对应步骤。

| 适配器 | MCP 工具 | 启用 | 说明 |
| :--- | :--- | :--- | :--- |
| `design-playbook-preview` | `preview_prototype` | `preview*` 人工确认门（G5） | 已打包；需系统 Edge/Chrome 弹窗（缺失回退默认浏览器） |
| `design-playbook-evidence` | `execute_capture_plan` | `observe*` 运行时取证（G6）——需 Playwright + Chromium | 已打包；取证在运行时仍可选 |

文档：[preview](./packages/design-playbook-preview/#install--mcp-config) · [evidence](./packages/design-playbook-evidence/#install--mcp-config)

## 🌐 跨平台安装

```bash
npx design-playbook init <agent>
# 或: python packages/design-playbook/scripts/generate_adapter.py <agent>
```

| 层级 | 平台 | 获得内容 |
| :--- | :--- | :--- |
| **Tier 1**（原生） | Claude Code、Codex | 完整保真——skills、commands、MCP、漂移检查快照 |
| **Tier 2**（生成） | Cursor、Gemini CLI、OpenCode、Windsurf、GitHub Copilot、Zed | skills 以各平台 rules 格式输出 + 项目级 MCP 配置；commands 降级为提示文档 |
| **Tier 3**（兜底） | Kiro、Amp、Jules、Qwen Code 等共 22 个——`npx design-playbook --list` | 含 orchestrator 合约 + MCP 安装指南的 `AGENTS.md` |

Claude Code 为原生平台。Tier 2/3 为生成适配器，已诚实说明降级内容。当前库存见[适配器矩阵](./packages/design-playbook/scripts/adapter_matrix.py)，分层语义见 [ADR-0042](./docs/adr/0042-multi-platform-adapter-generator.md)。

## 🔗 与生态组合

不是又一套风格/色板库——本插件管**交付链路、证据语义与验收闭环**，与其余各就其位：

| 包 | 用来做 |
| :--- | :--- |
| **design-playbook** | 参考? → 规格? → plan? → 骨架 → 可选 preview* → 填充 → 工艺检查 → 可选 observe* → point-back |
| [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 风格 / 色板 / 字体检索 |
| `frontend-design` | 反模板视觉方向 |
| [native-feel-skill](https://github.com/yetone/native-feel-skill) | 原生手感深度（WebView、IPC、内存） |

## 🪞 边界与实话

- **多模态**——截图内容理解依赖**宿主模型的视觉能力**。插件本身只做图片登记（locator + SHA-256 + metadata）；无视觉宿主改骑你给的文字说明。
- **Run Console**——已交付、状态 **experimental（实验性）**：本地单 run 控制台，把已有 run 产物投影成运营者可直接读的意图、来源判定、阻塞来源与下一 owner（含派生 Repair Packet，以及 `run-status` 发出的显式 `open-console` 延续动作）。保持**本地、受试用门禁约束**（尚未获得外部授权）、不是云端 Workspace、永远不会成为第二运行态权威。
- **MCP 打包配置**：marketplace 路径包含包内 MCP 运行时配置；registry 发布包可能未包含根 MCP 配置，需要宿主显式注册。
- **Windows 上的 Console loopback**：本地 Console 使用 loopback 传输；历史 dogfood 曾遇到传输中断，不能把本地 loopback 当作固定平台保证。
- **证明 vs 形态**——`scripts/validate_run.py` 机检的是 run 产物的*形态*与闭环轨迹；不宣称每个未来 run 自动就是高质量 UI。历史结论仅适用于各自记录的案例，不代表当前完整链路通过，也不是统计保证。

## 📄 许可

MIT（原创内容）。见 [`LICENSE`](./packages/design-playbook/LICENSE) + [`NOTICE`](./packages/design-playbook/NOTICE)。不主张任何第三方 playbook 内容的权利。

仓库结构、维护脚本与工程壳在门面之后：[package README](./packages/design-playbook/README.md) · [docs/agents](./docs/agents) · [贡献指南](./.github/CONTRIBUTING.zh-CN.md)。

GitHub Issues 只供使用者报告问题和反馈。内部 spec、plan、research 和工作票只留本地、不提交，
边界见[票据政策](./docs/agents/issue-tracker.md)。

维护者：[自动化验收](./docs/agents/automated-acceptance.md) 说明完整矩阵与独立项目操作流程回放。模拟审查输入只是回归夹具，不是外部试用证据。

---

<div align="center">

[English](README.md) · [实测展示](./packages/design-playbook/showcase) · [Releases](./docs/releases) · [Workflow](./docs/agents/product-workflow.md)

</div>
