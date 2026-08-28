<div align="center">

<img src="packages/design-playbook/showcase/screenshots/hero.png" alt="design-playbook — 给 coding agent 的 Design I/O" width="100%" />

# 🎴 design-playbook

### *Agent 交付的 UI 没人能验证。这个插件让它拿出证据。*

[![Version](https://img.shields.io/badge/Version-0.21.0-2DD4BF?style=flat-square&logo=semver&logoColor=black)](https://www.npmjs.com/package/design-playbook)
[![License](https://img.shields.io/badge/License-MIT-2DD4BF?style=flat-square&logo=opensourceinitiative&logoColor=black)](./packages/design-playbook/LICENSE)
[![Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-2DD4BF?style=flat-square&logo=claude&logoColor=black)](#-试一把)
[![Skills](https://img.shields.io/badge/Skills-8-2DD4BF?style=flat-square)](#-skills-与命令)
[![Commands](https://img.shields.io/badge/Commands-6-2DD4BF?style=flat-square)](#-skills-与命令)
[![Codex](https://img.shields.io/badge/Codex-ready-2DD4BF?style=flat-square)](./packages/design-playbook/codex/AGENTS.md)

</div>

---

## ⚡ 一条命令，三份产物

```text
/design-playbook:design-io <你的 UI 需求>
```

一次通过——MCP 工具已随包内置，零额外配置——在 `.scratch/<run>/` 落下三样产物：

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

Codex 安装细节、marketplace 不可用时的 `[mcp_servers.*]` 直配 fallback、preview 前置条件：见 [`packages/design-playbook/codex/AGENTS.md`](./packages/design-playbook/codex/AGENTS.md)。

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

</details>

## 📸 证据，不是承诺

Agent 永远不能悄悄给自己的作业打分：

- **Point-back**——每个验收发现都点名拥有它的 spec、领域规则或工艺声明。不存在无主的"看起来不错"。
- **回流（recirculate）**——blocking 发现回流到 owning 阶段直到闭环；闭环轨迹本身就是 run 产物的一部分。
- **不能静默跳过**——跳过审计仍会产出 point-back 骨架，但标记 `audited: false`，strict 校验不把它当已审计结果放行。

对 [SwarSight](./packages/design-playbook/showcase) 的一次完整实跑——真实第三方工作台，一行需求，每个关键产物都留了底：

| | |
| :---: | :---: |
| **1 · ux-spec**——写 UI 之前的六层 spec | **2 · ui-picker**——写代码之前的决策报告 |
| ![六层 spec](packages/design-playbook/showcase/screenshots/01-spec.png) | ![决策报告](packages/design-playbook/showcase/screenshots/02-decision-report.png) |
| **3 · ui-evaluator**——point-back + 回流闭环 | **结果**——六项检查全绿 |
| ![Point-back 发现](packages/design-playbook/showcase/screenshots/03-point-back.png) | ![六项检查全绿](packages/design-playbook/showcase/screenshots/04-gates.png) |

**人工确认门实况（`preview*`）**——生成的原型直接渲染在评审工作台里：spec 的验收准则以清单形式列在旁边（你的核对勾选随决策一并记录），可点选元素、拖拽高亮框、圈画、测量间距来锚定意见——然后签署放行或打回重做：

![Preview 确认工作台——批注后确认或打回](packages/design-playbook/showcase/screenshots/05-preview-confirm.png)

完整产物——spec、决策报告、point-back 评审、preview 人工确认演示、对本插件自身实测的运行界面：[`showcase/`](./packages/design-playbook/showcase)。

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

八个 model 触发 skill（`/design-playbook:<名>`）：

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

**命令**：`design-io`（全链路）· `ux-spec`（只出 spec）· `ui-review`（只验收）· `run-review`（跨 run 复盘）· `run-status`（阶段与恢复叙述）· `doctor`（安装面健康）

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

完整矩阵与重入语义见 [`docs/specs/ui-ux-vnext/loop-prototype.md`](./docs/specs/ui-ux-vnext/loop-prototype.md)。

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
| **Tier 2**（生成） | Cursor、Gemini CLI、OpenCode、Windsurf、GitHub Copilot | skills 以各平台 rules 格式输出 + 项目级 MCP 配置；commands 降级为提示文档 |
| **Tier 3**（兜底） | Kiro、Amp、Jules、Qwen Code 等共 22 个——`npx design-playbook --list` | 含 orchestrator 合约 + MCP 安装指南的 `AGENTS.md` |

Claude Code 为原生平台。Tier 2/3 为生成适配器，已诚实说明降级内容。完整能力矩阵：[docs/specs/2026-08-28-multi-platform-adapter.md](./docs/specs/2026-08-28-multi-platform-adapter.md)。

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
- **Run Console**——规划中：本地单 run 控制台，把已有 run 产物投影成运营者可直接读的意图、来源判定、阻塞来源与下一 owner。尚未发布、不是云端 Workspace、永远不会成为第二运行态权威。
- **证明 vs 形态**——`scripts/validate_run.py` 机检的是 run 产物的*形态*与闭环轨迹；不宣称每个未来 run 自动就是高质量 UI。showcase 是一次被演示的通过，不是统计保证。

## 📄 许可

MIT（原创内容）。见 [`LICENSE`](./packages/design-playbook/LICENSE) + [`NOTICE`](./packages/design-playbook/NOTICE)。不主张任何第三方 playbook 内容的权利。

仓库结构、维护脚本与工程壳在门面之后：[package README](./packages/design-playbook/README.md) · [docs/agents](./docs/agents)。

---

<div align="center">

[English](README.md) · [实测展示](./packages/design-playbook/showcase) · [Releases](./docs/releases) · [Workflow](./docs/agents/product-workflow.md)

</div>
