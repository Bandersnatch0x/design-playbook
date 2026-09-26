# 贡献指南

[English](CONTRIBUTING.md)

design-playbook 是为 coding agent 提供带证据 UI 交付的插件。本文说明仓库贡献流程，安装和使用方式见 README。

## 当前范围

项目处于维护者自用与维护阶段，catalog 提交和参与者招募均由维护者明确暂停。
正确性、安全和文档/漂移治理仍可进行。新增能力须按
[ADR-0045](../docs/adr/0045-external-evidence-spend-gate.md) 获得明确、有界的实施授权；
spec 或 open ticket 本身不是授权。恢复活动须经明确决定。内部 run 和自动夹具不能满足外部试验门禁。

## 从哪里读起

先读 [AGENTS.md](../AGENTS.md)、[CONTEXT.md](../CONTEXT.md) 和相关 [ADR](../docs/adr)。
spec、plan、research 和独立工作票是个人开发产物，全部只留本地，不放 `docs/`，不提交 Git。
本维护者使用已忽略的 `.agents/` 目录；其他贡献者无须采用相同目录、元数据格式或工作流。
公开规范与交付摘要须在干净检出可读，不依赖本地规划文件。
`.agents/` 的个人约束不适用于其他贡献者；个人资产、根目录 `.claude/` 命令与配置、`.scratch/` 产物不提交。
根目录和安装包内的 `.claude-plugin/` 是公开插件元数据，不是个人配置，应保留版本控制。
`.agents/` 内只有存量已跟踪的 `plugins/marketplace.json` 是分发例外，不扩大例外范围。
`.scratch/<run>/plan.md` 是产品 run 工件，不是仓库实施计划。

## 工作路由

1. 按[票据政策](../docs/agents/issue-tracker.md) 路由。GitHub Issues 只供使用者报告问题和反馈，不承载内部工作票。
   缺陷报告需提供预期/实际行为、包与宿主版本、最小复现及脱敏证据。
   内部规划只留本地；使用者反馈不构成新增能力的实施授权。
2. 非 bug 工作先确认范围，写明用户结果、非目标、权威边界、依赖与可观察验收标准。
   改契约或跨模块权威时先裁决 ADR。提案 spec 不覆盖已接受 ADR。
3. 编辑前确认实施授权并检查未解除阻塞。工作方法由贡献者自行选择；共享要求只限制文档和交付证据，
   不要求个人工作流或安装个人技能。保持改动聚焦，不覆盖无关改动。
4. 以窄而完整的用户路径实现，在已有公开接口增加回归测试。交付摘要记录验证与剩余限制，未运行不得记通过。

## 文档与交付

[文档入口](../docs/README.md) 按主题组织：架构说明组成与权威，子系统说明当前行为与契约，
开发/测试说明贡献与验证，`docs/adr/` 保留共享的长期决策，`docs/agents/` 放共享维护约定。
发布和退役记录保留历史事实。有真实读者任务时再增加使用指南或操作手册，不建立空分类。
个人规划和本次本地治理记录不能换个文档类型重新发布。

一个事实只有一个归属。动态清单链接到运行时 schema、生成器或 CI，不手抄第二份；
行为变化时同步所属说明。生成区必须标明生成器与 freshness 检查，不将人工解释标成生成内容。
中英配对文档同步修改；链接检查不证明语义等价或裁决授权。

交付摘要列明范围、可观察验收结果、实际检查、未跑项和剩余限制。
私有 spec/ticket 不能成为理解改动的唯一途径。移动或删除共享文档前检查入链与独有信息，
保留必要内容，取得删除授权；不把发布历史改写成当前状态。
链接检查拒绝公开导航依赖私有文件，也拒绝强制加入 Git 的个人产物；
`.gitignore` 本身不会取消已有跟踪。明确授权的历史 issue 迁移只落本地且不提交，
不授权持续镜像或删除后续使用者反馈，边界见票据政策。

## 验证与发布

先跑受影响的窄测试，再跑快速门：

```bash
python scripts/validate.py
python scripts/check_doc_links.py
python scripts/doctor.py --skip-self-check
```

修改 README 审计措辞还需运行
`python -m pytest -q tests/test_audit_preferences_prose.py`。
完整 pytest 与 Chromium 端到端矩阵以 [ci.yml](workflows/ci.yml) 为权威，
执行说明见[自动化验收](../docs/agents/automated-acceptance.md)。快速门不等于完整验收。
说明运行范围、结果及未运行项；用户可见 UI 改动附相关截图。

`main` 是稳定分发渠道，发布须走[发布清单](../docs/agents/release-checklist.md)。
本文不授权发布、catalog 提交或外部试验。

## 边界

- 可安装产品位于 `packages/design-playbook/`；同级包承担兼容启动器或桥接职责。
  声明 SSOT 位于包内 `skills/*/references/*`，复用现有权威 owner。
- 产品文案和示例必须自研；吸收外部思路用原创表达，遵循 AGENTS.md 的外部名词与署名规则。
- 生成的 `.codex-plugin/` 与 `codex/AGENTS.md` 不手改。版本变化后运行
  `python packages/design-playbook/scripts/generate_adapter.py codex` 并验证漂移门；无关文案编辑不刷新生成文件。
- 中英 README 和贡献指南保持事实一致。个人规划保留本地，仅发布必要的长期说明与决策，不发布规划文件；以链接替代规范复制。
- 密钥、凭证、原始私有项目数据和个人路径不写入报告或提交。不增加隐式遥测或自动上传。
  分享前检查 diff，包含截图和日志。
