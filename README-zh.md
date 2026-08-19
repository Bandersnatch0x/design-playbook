<div align="center">

<img src="packages/design-playbook/showcase/screenshots/hero.png" alt="design-playbook — 给 coding agent 的 Design I/O" width="100%" />

# 🎴 design-playbook

### *给 coding agent 的 Design I/O — 用声明 + 契约让 UI 生成可控、可验收、可回流。*

[![Version](https://img.shields.io/badge/Version-0.20.2-2DD4BF?style=flat-square&logo=semver&logoColor=black)](.#)
[![License](https://img.shields.io/badge/License-MIT-2DD4BF?style=flat-square&logo=opensourceinitiative&logoColor=black)](./packages/design-playbook/LICENSE)
[![Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-2DD4BF?style=flat-square&logo=claude&logoColor=black)](.#)
[![Skills](https://img.shields.io/badge/Skills-8-2DD4BF?style=flat-square)](.#)
[![Commands](https://img.shields.io/badge/Commands-4-2DD4BF?style=flat-square)](.#)
[![Codex](https://img.shields.io/badge/Codex-ready-2DD4BF?style=flat-square)](./packages/design-playbook/codex/AGENTS.md)

*不是又一套风格/色板库。与 `ui-ux-pro-max` + `frontend-design` 互补；本插件管**链路与验收**。*

</div>

---

## ✨ 它是什么

Claude Code / Codex 插件。每次跑同一条可预测链路 — **Design I/O**：`design-baseline? → reference-intake? → ux-spec? → plan? → (native-craft?) → ui-picker → (preview*) → fill → craft-guard† → (observe*†) → ui-evaluator†`，验收把每个问题**指回**所属声明，blocking 必须**回流**直到闭环。`?` 为条件入场：已有产品的 UI 修改先跑 `design-baseline?`，有截图/URL/设计稿/产品类比时再跑 `reference-intake?`；`preview*`/`observe*` 仅在对应可选 MCP 工具（`preview_prototype` / `execute_capture_plan`）存在时运行，否则跳过直进下一阶段。`†` = 用户可选的审计阶段（ADR-0033）：`craft-guard†` / `observe†` / `ui-evaluator†` 可由用户关闭 — 首次运行问一次，选择作为默认记入 `.design-playbook/preferences.yaml`（版本化；本机覆盖写在 `preferences.local.yaml`，已 gitignore）。跳过 `ui-evaluator†` 仍会生成标记 `audited: false` 的 point-back 骨架，strict 校验不会把它当作已审计结果放行。

- **声明** *（什么是好）*：`spec` · `domain` · `craft` · `design` · `components` · `template`
- **契约** *（怎么进链路）*：`skill`（时机）· `evaluator`（验收 + 回流）

> 🎬 **试一把**：`/design-playbook:design-io <需求>` — 一次通过产出 `spec.md`、决策报告与 point-back 台账，落在 `.scratch/<run>/`（产物形态见 [`showcase/01-spec.md`](./packages/design-playbook/showcase/01-spec.md)）。**真实项目实跑**：[`showcase/`](./packages/design-playbook/showcase) 是对 SwarSight 的一次完整 Design I/O 实测 — spec、决策报告、point-back 评审 + 闭环回流轨迹。

## 📦 安装

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

> Codex 安装细节、marketplace 不可用时的 `[mcp_servers.*]` 直配 fallback、preview 前置条件（系统 Chromium + python）：见 [`packages/design-playbook/codex/AGENTS.md`](./packages/design-playbook/codex/AGENTS.md)。`preview*`/`observe*` 仅在对应 MCP 工具注册后运行，否则编排器**静默跳过**（不是报错）。

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

Codex bridge 说明：[`packages/design-playbook/codex/AGENTS.md`](./packages/design-playbook/codex/AGENTS.md)。

</details>

调用一律**带命名空间**：`/design-playbook:design-io <需求>`。裸 `/design-io` 仅 `--plugin-dir` 开发态别名。

## 🧩 Skills 与命令

八个 model 触发 skill（`/design-playbook:<名>`）：

| Skill | 职责 |
| :--- | :--- |
| `design-playbook` | 🎯 编排（全链路；run-profile 档位定档 P1/P2/P3） |
| `design-baseline` | 🧭 初始化发现、校验或从已有 UI 生成项目 `DESIGN.md` 草稿 |
| `reference-intake` | 📎 参考契约（截图/URL/类比 → Keep/Change/Do not copy） |
| `ux-spec` | 📋 六层 spec 声明（S0-S6 成形会话：问题/假设/确认批次 + 会话工件） |
| `ui-picker` | 🧱 骨架 + 组件语义 + R/C/E 设计决策条目 |
| `craft-guard` | 🛡️ 工艺 / 反 AI 味（第一方规则注册表 + 七列审计行） |
| `native-craft` | 🖥️ 桌面原生手感声明 |
| `ui-evaluator` | ✅ 双轨验收（六块 point-back 报告）+ 回流 |

**命令**：`design-io`（全链路）· `ux-spec`（只出 spec）· `ui-review`（只验收）· `run-review`（跨 run 复盘）· `run-status`（阶段与恢复叙述）· `doctor`（安装面健康）

## 🎚️ Run 档位（P1/P2/P3）

每个 run 在 `plan.md` **run-profile** 块声明档位——流程重量与变更后果成正比。代理按声明触碰面判据初判、用户一次确认；**升档自动**（纠偏信号一出现即升档并补走新增环节），降档需用户。

| 档 | 范围 | 门禁面 |
| :--- | :--- | :--- |
| **P1** 点修 | 单一 owning 层 point-back 修复，不触碰 decided 字段 | 注册表子集求值；R4/R5（+R2 行级）路由 |
| **P2** 标准 | 基线内功能变更（新判据、R/C 决策） | 适用谓词全求值；成形会话 + G9/G10 |
| **P3** 全量 | decided 字段修订（supersedes）、结构性重构、E 档决策 | G1-G12 全谱 + 采样矩阵完整执行 |

完整矩阵与重入语义见 [`docs/specs/ui-ux-vnext/loop-prototype.md`](./docs/specs/ui-ux-vnext/loop-prototype.md)。

## 🔗 与生态组合

| 包 | 用来做 |
| :--- | :--- |
| **design-playbook** | 参考? → 规格? → plan? → 骨架 → 可选 preview* → 填充 → 工艺 → 可选 observe* → point-back |
| [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 风格 / 色板 / 字体检索 |
| `frontend-design` | 反模板视觉方向 |
| [native-feel-skill](https://github.com/yetone/native-feel-skill) | 原生手感深度（WebView、IPC、内存） |

## 🔌 适配器（v0.3+ 随主插件打包）

Preview / Evidence MCP 运行时已放进主插件（`packages/design-playbook/mcp/` +
带 `${CLAUDE_PLUGIN_ROOT}` 的 `.mcp.json`）。marketplace 安装后即可注册两个工具，
无需第二包。orchestrator 仍会**探测**；宿主无 MCP 工具时跳过对应步骤。

| 适配器 | MCP 工具 | 启用 | 说明 |
| :--- | :--- | :--- | :--- |
| `design-playbook-preview` | `preview_prototype` | `preview*` 人工确认门（G5） | 已打包；需系统 Edge/Chrome 弹窗（缺失回退默认浏览器）；兄弟目录为兼容 launcher |
| `design-playbook-evidence` | `execute_capture_plan` | `observe*` 运行时取证（G6）——需 Playwright + Chromium | 已打包；取证在运行时仍可选 |

文档：[preview](./packages/design-playbook-preview/#install--mcp-config) · [evidence](./packages/design-playbook-evidence/#install--mcp-config)

## 🗂️ 目录结构

```text
.claude-plugin/marketplace.json   ← 仓库根 catalog（source: ./packages/design-playbook）
packages/design-playbook/         ← 公开插件（skills、commands、mcp/、examples、showcase）
packages/design-playbook/mcp/     ← 打包的 Preview + Evidence MCP 运行时
packages/design-playbook-preview/ ← 兼容 launcher + 文档（G5）
packages/design-playbook-evidence/← 兼容 launcher + 文档（G6）
docs/agents/  docs/adr/           ← 工程壳（tracker、workflow、决策）
CONTEXT.md  .scratch/             ← 词汇表、spec、票、dogfood 日志
```

运行产物落在你项目的 `.scratch/<run>/` 下——见[package README](./packages/design-playbook/README.md)与 `SKILL.md` steps 3、5、8。

**维护脚本：** `scripts/doctor.py`（安装健康检查）、`packages/design-playbook/scripts/run_status.py`（从 run 产物推导 status/resume）、`scripts/release.py`（发版门禁）、`scripts/validate.py`（静态插件表面）。

仓库根 = GitHub 门面 + 工程壳 · package = 唯一运行时表面 · `product-*` 维护命令只留根，绝不进 package。

## 📄 许可

MIT（原创内容）。见 [`LICENSE`](./packages/design-playbook/LICENSE) + [`NOTICE`](./packages/design-playbook/NOTICE)。不主张任何第三方 playbook 内容的权利。

---

<div align="center">

[English](README.md) · [实测展示](./packages/design-playbook/showcase) · [Workflow](./docs/agents/product-workflow.md)

</div>
