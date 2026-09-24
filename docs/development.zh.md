# 开发说明

先读[贡献指南](../.github/CONTRIBUTING.zh-CN.md)确认改动范围，再按[架构](architecture.zh.md)定位所属包。安装、运行时依赖和宿主使用方式以[安装包说明](../packages/design-playbook/README.md)为准；测试依赖以 [CI](../.github/workflows/ci.yml) 为准。

## 本地验证路径

1. 在现有公开接口为本次行为添加或更新回归测试。
2. 运行受影响测试，再跑 `python scripts/validate.py`、`python scripts/check_doc_links.py` 和 `python scripts/doctor.py --skip-self-check`。
3. 修改交互行为时跑相应 Chromium 回归；完整范围见[测试说明](testing.zh.md)。
4. 交付摘要写明实际结果、未跑项和限制。工作树验证通过不等于已经发布。

包内声明与生成模板是改动入口；生成快照不要手改。发布操作与版本同步按[发布清单](agents/release-checklist.md)执行，不把日常文档修改变成发布授权。

## 文档跟随行为

改组成或权威边界时更新架构说明，改具体运行行为时更新所属子系统，改长期裁决时更新 ADR。只在一个归属维护事实，其他入口用链接。中英 README 与贡献指南保持一致。

个人规划、研究和工作票仅本地保留，不要求其他贡献者安装个人技能或复现个人流水线。使用者反馈与已授权历史 issue 迁移的边界见[票据政策](agents/issue-tracker.md)；范围和交付结果必须能脱离个人记录读懂。
