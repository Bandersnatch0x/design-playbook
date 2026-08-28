# Product workflow — design-playbook

主线：把 **packages/design-playbook** 打磨成可公开安装、过程可预测的 Design I/O 插件。

## 北极星（v0）

一次 `/design-io`（编排序列 SSOT 见 `packages/design-playbook/skills/design-playbook/SKILL.md`）：

`design-baseline? → reference-intake? → ux-spec? → plan? → (native-craft?) → ui-picker → (preview*) → fill → craft-guard† → (observe*†) → ui-evaluator†`

（`†` = 用户可选审计阶段，ADR-0033：首次运行问一次，记入 `.design-playbook/preferences.yaml`）

1. 已有产品做 UI build/fix 时先 `design-baseline?`：`prepare` → 确认/waiver → `verify`；门禁工件仅为 `design-baseline/state.json`；缺失或过期则从第一方 UI 生成草稿，确认或显式 waiver 后才能 Fill（ADR-0012）
2. 有截图/URL/设计稿/产品类比时跑 `reference-intake?`（`.scratch/<run>/reference/`；非 gate，ADR-0011）
3. L5/L6 `spec.md`（缺则先 ux-spec，并消费 reference 功能约束；有则 plan 轻量交接）
4. 写码前 decision report（`ui-picker` 止于 report；引用 project `DESIGN.md` 路径 + hash，并消费 reference 视觉线索）
5. 可选 `preview*`（MCP `preview_prototype` 存在才跑；确认后才进 Fill；G5 条件 gate）
6. point-back 验收；可选 `observe*` 在 craft 后、验收前从宿主运行态采集 criterion-addressable 证据（manifest bind，ledger observed 引用 `evidence/` 工件；G6 条件 gate）
7. blocking 回流声明层
8. 陌生人可复制安装（package README）

## 阶段

```text
0 setup       done
1 grill       → CONTEXT + ADRs
2 dogfood     → /product-dogfood（process only）
3 to-spec     → .scratch/design-playbook-v0/spec.md
4 to-tickets  → .scratch/design-playbook-v0/issues/
5 implement*  → 每票清上下文；改 packages/design-playbook/**
6 polish      → 再 dogfood + writing-great-skills
```

规则：

- 1→4 同一上下文；顶 smart zone 用 handoff。  
- implement 每票新会话。  
- **只改 package 内自有表面**；禁止搬迁上游正文/图。  
- references 剔除 playbook 特化示例（改写为通用）。

## 命令

安装包内六命令（`packages/design-playbook/commands/`，签名 v0 起零改动；描述随 vNext 深化）：

| 命令 | 职责 | vNext 面 |
| --- | --- | --- |
| `design-io` | 全链路编排入口 | run-profile 档位定档（P1/P2/P3）与回流循环 |
| `ux-spec` | 只出 spec | 成形会话（问题/假设/确认批次）与会话工件；止于 spec.md |
| `ui-review` | 只验收 | 双轨评审 + 六块 point-back 报告 |
| `run-review` | 跨 run 复盘 | 规则候选队列（派生视图，只呈报不写回） |
| `run-status` | run 状态读模型 | 识别 run-profile/成形会话/invalidated 重入叙述 |
| `doctor` | 安装面健康诊断 | 零改动（rules.md 属包内工件由 validate.py 校验） |

维护者命令 `product-next / product-grill / product-dogfood` 在 monorepo `.claude/commands/`（不进安装包）。

## vNext 工件面（S1-S6 落地）

规格权威：[`docs/specs/ui-ux-vnext/`](../specs/ui-ux-vnext/)（八份定稿原型 + 切片图）。落码要点：

- **档位**：每个 run 的 `plan.md` 头部必写 `run-profile` 结构化块（tier P1|P2|P3 + 判据核对 + 跳过清单 + 升档事件）；升档自动、降档需用户；G12 机器复盘。
- **成形**：`ux-spec` S0-S6 会话工件 `.scratch/<run>/shaping/`（shaping-log.jsonl + 派生 queue.json），G9 校验出口。
- **规则**：注册表 `skills/design-playbook/references/rules.md`（G8 产品级 + run 级共享解析器）；项目级治理日志 `rules-governance.jsonl`（仅用户决定性事件）。
- **设计决策**：decision-report 顶块后追加 DD 条目块（R/C/E 三档，G10）；E 档确认搭乘 preview 事务。
- **评审**：point-back 六块报告（+Positive/Coverage/Limitations）+ `invalidated:` 失效集 + finding 附加字段；G11 消费 Coverage statement（P3 档强制五态×页面采样矩阵块）。
- **示例**：`packages/design-playbook/examples/`（export-entry P2 / export-upgrade P3 / dogfood S6 自举全链 / rules-governance 治理走查）。

## 票夹

`.scratch/design-playbook-v0/`

## v0 ship 勾选

- [ ] CONTEXT + ADR 覆盖范围/许可/SSOT/仓形态
- [ ] package README 安装路径可复制
- [ ] references 无上游特化残留
- [ ] ≥2 次 dogfood 过程门通过
- [ ] issues 全 resolved 或 wontfix

## Release gate

见 [`release-checklist.md`](release-checklist.md)：五步门 + semver tag。静态部分由 CI（`.github/workflows/ci.yml` -> `scripts/validate.py`）自动跑；会话级步骤仍手动。`git init` + 公开 remote 是公开 claim 的硬前置（ADR-0006 / 票 06）。

## Bundled MCP adapters（G5 preview / G6 evidence）

Preview 与 Evidence 的 MCP 运行时随主插件打包（`packages/design-playbook/mcp/` + 带 `${CLAUDE_PLUGIN_ROOT}` 的 `.mcp.json`）；marketplace 安装即注册 `preview_prototype` 与 `execute_capture_plan` 两个工具，无需第二个包。`packages/design-playbook-preview/`、`packages/design-playbook-evidence/` 仅是兼容 launcher + 文档。orchestrator 仍按存在性探测：`preview*` 确认后才进 Fill（G5）；`observe*` 依 spec L6 派生 capture plan，产物绑定进 `.scratch/<run>/evidence/manifest.jsonl`（G6）——binding 与 verdict 归 design-playbook，runtime 永远归 provider。

适配器缺席不降级协议：缺席 = 显式 `blocked` / `not-applicable` 记录或既有通道回落，永不静默跳过、永不臆断 pass（vnext-prototype 第 4 节；预览缺席记 run-profile 跳过清单一行，取证缺席记 ledger `result: blocked` 回流 R5）。

## 跨平台适配器（ADR-0042）

`npx design-playbook init <agent>`（npm bin 壳 → `packages/design-playbook/scripts/generate_adapter.py`）从 canonical `skills/` / `commands/` / `mcp/` 渲染各平台产物，三层保真：Tier1 全保真（Claude Code、Codex——Codex 快照为生成后提交，`validate.py` / `doctor.py` 防漂移门禁校验）；Tier2 skills+MCP（Cursor、Gemini CLI、OpenCode、Windsurf、Copilot）；Tier3 AGENTS.md 地板（其余 22 agent）。生成产物禁止手改；**版本升级后必须重跑 `generate_adapter.py codex` 刷新快照**。能力矩阵：`docs/specs/2026-08-28-multi-platform-adapter.md`。
