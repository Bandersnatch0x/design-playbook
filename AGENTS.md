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
| 多平台 adapters | `packages/design-playbook/scripts/generate_adapter.py` + `adapter_matrix.py` + `adapter_templates/`（ADR-0042；`npx design-playbook init`，30-agent 三层矩阵） |
| npm / pi | `packages/design-playbook/package.json`（`pi` manifest + `pi-package` keyword → pi.dev gallery） |
| 自有示例 | `packages/design-playbook/examples/` |
| 产品 workflow | `docs/agents/product-workflow.md` |
| 中文文档 | `docs/README.md` · `docs/architecture.zh.md` |
| 词汇 / ADR | `CONTEXT.md` · `docs/adr/` |

与第三方风格库、反模板类 skill 互补（生态署名见 README 叠加表）；本包管链路与验收。

## Agent skills

### Issue tracker

GitHub Issues in `Bandersnatch0x/design-playbook` are **for user reports and feedback only**, handled with `gh`. Internal specs, plans, research, and work tickets stay local and untracked. Historical issue migration is a one-time authorized operation, not permission to delete future reports. See [issue policy](docs/agents/issue-tracker.md).

### Triage labels

Canonical GitHub issue labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.

### Product commands

产品命令位于 `packages/design-playbook/commands/`。根目录 `.claude/` 的个人命令与配置只留本地，不提交、不作为贡献前提；`.claude-plugin/` 是公开分发元数据，继续跟踪。

### Documentation and delivery

`docs/` 只放面向维护者和使用者的长期文档。spec/plan/research/issues/tickets 全部本地保留，不提交 Git；本维护者统一放 `.agents/`，不要求其他贡献者采用个人目录或格式。创建、修改或归档时读[贡献指南](.github/CONTRIBUTING.zh-CN.md)。

每次交付记录范围、验收结果、未跑项与限制；可机械判定的新约束接入现有门禁并加反例测试。个人流程与 skill 选择不约束其他维护者；`.agents/` 中的个人资产不提交、不作为共享规范的依赖。

## 开发注意

1. **公开可分发表面**仅 package 内自有内容——文案与自研 MCP runtime（ADR-0003、ADR-0009）；改 skill 勿从任何上游/旧 attachments 同步。  
2. **SSOT** = `packages/design-playbook/skills/*/references/*`（ADR-0004）。  
3. 演示站已移除；勿再引入 `src/` 阅读站作为交付。  
4. 打磨产品时先读 `CONTEXT.md` 当前指针和相关 ADR，再读本任务 plan/ticket；旧 phase 只作历史线索，缺失不阻断新任务。
5. skill 文案变更遵循 writing-great-skills（完成标准、少重复、pointers）。  
6. **生成快照勿手改**：`packages/design-playbook/{.codex-plugin/,codex/AGENTS.md}` 由生成器产出——版本号变更后运行 `python packages/design-playbook/scripts/generate_adapter.py codex`，否则 validate/doctor 漂移门失败（ADR-0042）。  
7. **外部名词边界**：产品内容（skills、references、rules.md、术语表）与本文件零外部产品/skill 名——吸收外部思路一律自研措辞，注册表条目标 `provenance: benchmark-input-only`；README 生态署名表与 codex 路由行是既定豁免（ADR-0002；validate.py 署名/路由豁免）。  
8. **文档与个人产物分离**：长期共享说明进 `docs/`；个人规划进本地 `.agents/`，个人命令与配置留根目录 `.claude/`，临时产物进 `.scratch/`，三者不提交 Git（`.agents/plugins/marketplace.json` 存量分发文件除外）。产品示例、测试夹具和运行时契约不按同名文件误迁；根级不新增杂项目录。

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
