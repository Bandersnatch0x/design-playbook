# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目是什么

**design-playbook** — coding agent 的 **UI Design I/O 插件**（声明 + 契约 + 回流）。  
可安装包：`packages/design-playbook/`。本仓**参考**通用 Design I/O 思路，**不是**上游 playbook 的叠加或搬迁。

| 层 | 路径 |
| --- | --- |
| Plugin 元数据 | `packages/design-playbook/.claude-plugin/plugin.json` |
| Skills | `packages/design-playbook/skills/{design-playbook,reference-intake,ux-spec,ui-picker,craft-guard,native-craft,ui-evaluator}/` |
| Commands | `packages/design-playbook/commands/` |
| MCP adapters | `packages/design-playbook/mcp/{preview,evidence}/` + 包根 `.mcp.json`（ADR-0009；sibling 包为兼容启动器） |
| Codex | `packages/design-playbook/codex/AGENTS.md` |
| 自有示例 | `packages/design-playbook/examples/` |
| 产品 workflow | `docs/agents/product-workflow.md` |
| 阶段指针 | `.scratch/design-playbook-v0/phase.md` |
| 词汇 / ADR | `CONTEXT.md` · `docs/adr/` |

与 ui-ux-pro-max（风格库）、Anthropic `frontend-design`（反模板）互补；本包管链路与验收。

## Agent skills

### Issue tracker

Local markdown under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

`Status:` line roles. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.

### Product workflow

grill → dogfood → to-spec → to-tickets → implement → polish.  
Commands live under `packages/design-playbook/commands/` (pipeline) and monorepo `.claude/commands/` (`product-next`, `product-grill`, `product-dogfood`).

## 开发注意

1. **公开可分发表面**仅 package 内自有内容——文案与自研 MCP runtime（ADR-0003、ADR-0009）；改 skill 勿从任何上游/旧 attachments 同步。  
2. **SSOT** = `packages/design-playbook/skills/*/references/*`（ADR-0004）。  
3. 演示站已移除；勿再引入 `src/` 阅读站作为交付。  
4. 打磨产品时先读 `.scratch/design-playbook-v0/phase.md` 与 `CONTEXT.md`。  
5. skill 文案变更遵循 writing-great-skills（完成标准、少重复、pointers）。

## 安装自测

```text
# path of record (catalog at repo root)
/plugin marketplace add <owner>/<repo>            # or <abs-to-repo-root> locally
/plugin install design-playbook@design-playbook
# dev load
claude --plugin-dir <abs>/packages/design-playbook
```

调用一律 namespaced：`/design-playbook:design-io`。bare `/design-io` 仅 `--plugin-dir` 开发态别名。
