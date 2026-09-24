# 文档入口

这里说明 design-playbook 的当前使用方式、组成和维护边界，不存个人开发过程记录。

| 你要做什么 | 从哪里开始 |
| --- | --- |
| 安装并运行插件 | [中文 README](../README-zh.md)、[安装包说明](../packages/design-playbook/README.md) |
| 理解系统组成与事实归属 | [架构](architecture.zh.md)、[领域词汇](../CONTEXT.md) |
| 修改预览、取证或交付 | [运行时子系统](subsystems/runtime.zh.md) |
| 理解 Console 状态与来源 | [Run Console](subsystems/run-console.zh.md) |
| 开发与提交改动 | [开发说明](development.zh.md)、[贡献指南](../.github/CONTRIBUTING.zh-CN.md) |
| 选择验证范围 | [测试说明](testing.zh.md) |
| 查当前方向与冻结边界 | [产品方向](roadmap.md) |
| 查决策理由 | [ADR](adr/) |
| 查发布与退役历史 | [发布记录](releases/)、[退役记录](deprecations/) |

`docs/agents/` 是共享维护约定，个人流程不是贡献前提。spec、plan、research、issues/tickets 全部只留本地，不提交 Git；GitHub 只供使用者报告问题和反馈，历史 issue 的一次性本地迁移见[票据政策](agents/issue-tracker.md)。

这些中文说明是人工维护的参考文档，不是从源码生成的 API 清单。运行字段以链接的 schema 和实现为准，决策理由以 ADR 为准；文档与交付规则归[贡献指南](../.github/CONTRIBUTING.zh-CN.md)。

历史文档也按内容分离：工期安排、任务清单、个人审计和执行记录只留本地；有长期读者的操作方法、契约与验收边界保留为自包含说明。发布记录和共享 ADR 保留历史，后续裁决通过明确修订说明替代关系。
