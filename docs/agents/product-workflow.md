# Product workflow — design-playbook

主线：把 **packages/design-playbook** 打磨成可公开安装、过程可预测的 Design I/O 插件。

## 北极星（v0）

一次 `/design-io`：

1. L5/L6 `spec.md`
2. 写码前 decision report
3. point-back 验收
4. blocking 回流声明层
5. 陌生人可复制安装（package README）

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
