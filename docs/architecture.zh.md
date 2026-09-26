# 架构

design-playbook 将 UI 工作组织成“声明、实现、证据、回流”。插件帮助 agent 遵循契约，但不会把 agent 的判断自动升级为用户确认，也不会把截图存在当成验收通过。

## 组成

可安装产品位于 [packages/design-playbook](../packages/design-playbook/)。Skills 声明工作契约，commands 提供调用入口，Python 脚本验证工件。声明规范归 `skills/*/references/*`；[编排 skill](../packages/design-playbook/skills/design-playbook/SKILL.md) 指向各阶段所需的契约。

[包内 MCP 配置](../packages/design-playbook/.mcp.json) 注册 Preview 与 Evidence。它们分别提供交互确认和运行态采集。Run Console 是按需启动的本地 Web 运行时，不是第三个 MCP server。同级 preview/evidence 包是兼容启动器，桥接包也不拥有另一份产品逻辑。打包理由见 [ADR-0009](adr/0009-bundled-mcp-adapters.md)。

跨平台输出由 [adapter_matrix.py](../packages/design-playbook/scripts/adapter_matrix.py) 和 [生成器](../packages/design-playbook/scripts/generate_adapter.py) 派生；能力层级见 [ADR-0042](adr/0042-multi-platform-adapter-generator.md)。维护者改源模板，不直接修改生成快照。

## 一次运行

1. 将目标与可验收条件写入 run 声明；已有产品先按契约确认设计基线。
2. 在 Fill 前形成设计决策；适用时用 Preview 确认候选方案。
3. 实现后采集工件，由 manifest 绑定到明确的验收判据。
4. 评审引用声明与证据；阻塞问题回到对应声明层，修复后重新验证受影响部分。

档位、条件检查及重入语义见 [ADR-0029](adr/0029-vnext-closed-loop-final-state.md)。这里只说明阶段关系，不维护另一份 gate 或命令清单。

## 权威边界

| 内容 | 权威归属 | 不能替代它的内容 |
| --- | --- | --- |
| 用户意图与确认 | 已确认的声明、对应确认事务 | 研究推测、agent 自评 |
| 验收证据 | 判据绑定及有效运行工件 | 未绑定截图、文件名、口头完成声明 |
| 运行状态 | 既有状态投影读取的源事实 | Console 自建状态、个人进度票 |
| 发布事实 | 对应 release record/tag 与发布事务 | 当前工作树、规划里的完成状态 |

run 工件位于使用项目的 `.scratch/<run>/`，与本仓个人研发规划不是一回事。仓库 spec/plan/research/ticket 只留本地；这不迁移产品示例、测试夹具或运行时 schema。

修改底层行为前读[运行时说明](subsystems/runtime.zh.md)；修改读模型前读 [Run Console](subsystems/run-console.zh.md)。共享文档必须不依赖任何人的本地规划历史。
