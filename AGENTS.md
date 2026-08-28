# AGENTS.md

Guidance for coding agents (Claude Code / Codex / Qoder / …) working in this repository.

## 项目是什么

**design-playbook** — coding agent 的 **UI Design I/O 插件**（声明 + 契约 + 回流）。  
可安装包：`packages/design-playbook/`。本仓**参考**通用 Design I/O 思路，**不是**上游 playbook 的叠加或搬迁。

| 层 | 路径 |
| --- | --- |
| Plugin 元数据 | `packages/design-playbook/.claude-plugin/plugin.json` |
| Skills | `packages/design-playbook/skills/{design-playbook,design-baseline,reference-intake,ux-spec,ui-picker,craft-guard,native-craft,ui-evaluator}/` |
| Commands | `packages/design-playbook/commands/` |
| MCP / Console runtimes | `packages/design-playbook/mcp/{preview,evidence,run_console}/` + 包根 `.mcp.json`（ADR-0009；run console ADR-0037；sibling 包为兼容启动器） |
| Cordis 插件 | `packages/design-playbook/lib/index.js`（DSH skill provider + commands 注册；ADR-0003） |
| DSH MCP 桥接包 | `packages/dsh-design-playbook/`（薄 bundle，桥接 preview/evidence MCP；ADR-0009；CI workflow `.github/workflows/release-dsh-bundle.yml`，与 main 同 `v*` tag 模式） |
| 多平台 adapters | `packages/design-playbook/scripts/generate_adapter.py` + `adapter_matrix.py` + `adapter_templates/`（ADR-0042；`npx design-playbook init`，29-agent 三层矩阵） |
| npm / pi | `packages/design-playbook/package.json`（`pi` manifest + `pi-package` keyword → pi.dev gallery） |
| 自有示例 | `packages/design-playbook/examples/` |
| 产品 workflow | `docs/agents/product-workflow.md` |
| 阶段指针 | `.scratch/design-playbook-v0/phase.md` |
| 词汇 / ADR | `CONTEXT.md` · `docs/adr/` |

与第三方风格库、反模板类 skill 互补（生态署名见 README 叠加表）；本包管链路与验收。

## Agent skills

### Issue tracker

GitHub Issues in `Bandersnatch0x/design-playbook` carry **bug tickets only**, operated with `gh`; specs, research, and non-bug work tickets live locally under `.agents/` (gitignored). See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical GitHub issue labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.

### Product workflow

grill → dogfood → to-spec → to-tickets → implement → polish.  
Commands live under `packages/design-playbook/commands/` (pipeline) and monorepo `.claude/commands/` (`product-next`, `product-grill`, `product-dogfood`).

### Dev workflow

任务级流水线：路由 → 探路 → 拷问 → 成谱 → 成票 → 落码 → 验收，外加两个横切机制（出方案时的检验追问、决策点的圆桌辩论）与三条粘性规则（点名即常驻、裁决批次、自研措辞）。驱动命令 `/dev-next`（`.claude/commands/`）。See `.agents/dev-workflow.md`（本地，不入库）.

## 开发注意

1. **公开可分发表面**仅 package 内自有内容——文案与自研 MCP runtime（ADR-0003、ADR-0009）；改 skill 勿从任何上游/旧 attachments 同步。  
2. **SSOT** = `packages/design-playbook/skills/*/references/*`（ADR-0004）。  
3. 演示站已移除；勿再引入 `src/` 阅读站作为交付。  
4. 打磨产品时先读 `.scratch/design-playbook-v0/phase.md` 与 `CONTEXT.md`。  
5. skill 文案变更遵循 writing-great-skills（完成标准、少重复、pointers）。  
6. **生成快照勿手改**：`packages/design-playbook/{.codex-plugin/,codex/AGENTS.md}` 由生成器产出——版本号变更后运行 `python packages/design-playbook/scripts/generate_adapter.py codex`，否则 validate/doctor 漂移门失败（ADR-0042）。  
7. **外部名词边界**：产品内容（skills、references、rules.md、术语表）与本文件零外部产品/skill 名——吸收外部思路一律自研措辞，注册表条目标 `provenance: benchmark-input-only`；README 生态署名表与 codex 路由行是既定豁免（ADR-0002；validate.py 署名/路由豁免）。  
8. **agent 产物只进两处**：临时产物进 `.scratch/`，持久 agent 资产进 `.agents/`——根级不再新增 dot 目录；存量杂项目录各自退役时直接删除，不迁移。

## 校验与发布

- 提交前快速门：`python scripts/validate.py` · `python scripts/check_doc_links.py` · `python scripts/doctor.py --skip-self-check`；完整矩阵（pytest + chromium e2e）以 `.github/workflows/ci.yml` 为准。
- 发布走 release transaction：`python scripts/release.py`（dry-run）→ `--apply` 打 tag；人工步骤与四脚本分工见 `docs/agents/release-checklist.md`；`stable main` / `release transaction` 语义见 `CONTEXT.md`。

## 安装自测

```text
# path of record (catalog at repo root)
/plugin marketplace add https://github.com/Bandersnatch0x/design-playbook.git  # or <abs-to-repo-root> locally
/plugin install design-playbook@design-playbook
# dev load
claude --plugin-dir <abs>/packages/design-playbook
```

调用一律 namespaced：`/design-playbook:design-io`。bare `/design-io` 仅 `--plugin-dir` 开发态别名。
