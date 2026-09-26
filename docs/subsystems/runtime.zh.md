# Preview、Evidence 与交付

这三个职责分开：Preview 收集方案确认，Evidence 采集运行工件，handoff 构造可交付结果。确认设计不是确认实现通过；采集成功也不是验收通过。

## Preview

[Preview 运行时](../../packages/design-playbook/mcp/preview/) 承载候选界面、反馈与确认事务。[预览操作契约](../../packages/design-playbook/skills/design-playbook/references/preview-ops.md) 定义 agent 如何使用它；[ADR-0013](../adr/0013-preview-decision-transaction.md) 记录事务边界。

是否可继续 Fill 由确认工件及校验结果决定，不以浏览器窗口关闭、HTTP 请求成功或 agent 的文字声明代替。调整前端按钮、标注或版本交互时，必须保持确认事务语义，并运行对应浏览器回归。

## Evidence

[Evidence 说明](../../packages/design-playbook/mcp/evidence/README.md) 维护采集输入、运行根目录和限制。`execute_capture_plan` 产出截图或交互工件，但不直接授予判据 pass，也不替 agent 写证据 manifest。

绑定步骤使用 [evidence_manifest.py](../../packages/design-playbook/scripts/evidence_manifest.py)。缺失、错绑或过期证据必须暴露，不能因“文件存在”就视为满足判据。采集过程与绑定过程的分工见[取证操作契约](../../packages/design-playbook/skills/design-playbook/references/observe-ops.md)。

宿主进程工作目录不一定是当前聊天项目。跨项目取证时显式给出绝对 run 根，检查返回的 `written_path`；不要在未知目录下搜索到同名截图后补写成功结论。

## 静态交付

[run_handoff.py](../../packages/design-playbook/scripts/run_handoff.py) 从显式 run 及其 fill 声明构造交付。交付结果保留真实 verdict 和 authority；`Pending` 不会因为生成了压缩包就变成通过。

交付页、披露与文件访问的所有权见 [ADR-0034](../adr/0034-static-handoff-ownership-and-lifecycle.md)。修改导出或路径处理时覆盖越界、符号链接和缺失输入的拒绝行为，不只测试正常包生成。

验证入口见[测试说明](../testing.zh.md)。本文不复刻 MCP 参数表或 schema，字段变更同时更新对应实现契约和测试。
