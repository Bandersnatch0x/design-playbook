# Product workflow — design-playbook

主线：把 **packages/design-playbook** 打磨成可公开安装、过程可预测的 Design I/O 插件。

## 北极星（v0）

一次 `/design-io`（编排序列 SSOT 见 `packages/design-playbook/skills/design-playbook/SKILL.md`）：

`ux-spec? → plan? → (native-craft?) → ui-picker → (preview*) → fill → craft-guard → (observe*) → ui-evaluator`

1. L5/L6 `spec.md`（缺则先 ux-spec；有则 plan 轻量交接）
2. 写码前 decision report（`ui-picker` 止于 report）
3. 可选 `preview*`（MCP `preview_prototype` 存在才跑；确认后才进 Fill；G5 条件 gate）
4. point-back 验收；可选 `observe*` 在 craft 后、验收前从宿主运行态采集 criterion-addressable 证据（manifest bind，ledger observed 引用 `evidence/` 工件；G6 条件 gate）
5. blocking 回流声明层
6. 陌生人可复制安装（package README）

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

| 命令 | 位置 |
| --- | --- |
| product-next / product-grill / product-dogfood | monorepo `.claude/commands/` (not in installable package) |
| design-io / ux-spec / ui-review | `packages/design-playbook/commands/` |

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

## Optional preview adapter

Sibling package `packages/design-playbook-preview/` (stdio MCP, tool `preview_prototype`). Independent install; design-playbook does not package-depend. Wire via repo-root `.mcp.json` or host MCP config. See package README.

## Optional evidence provider

`observe*` probes for an external MCP tool `execute_capture_plan` (e.g. Playwright MCP). When present, the orchestrator derives a capture plan from spec L6, a provider executes it producing an artifact, and the orchestrator binds it to the criterion in `.scratch/<run>/evidence/manifest.jsonl`. When absent, `ui-evaluator` ledger `observed` stays free-text (current behavior) and G6 does not trigger. design-playbook owns the binding (manifest) and the verdict (ledger), never the runtime.
