# Run Console

Run Console 是单个 run 的本地查看与有限操作界面。它呈现意图、状态、阻塞来源和可执行动作，不建立另一套工作流状态。成熟度与角色边界见 [ADR-0036](../adr/0036-invited-trial-data-and-role-boundary.md)，当前能力投入限制见 [ADR-0045](../adr/0045-external-evidence-spend-gate.md)；能够启动界面不表示获准外部试用。

## 从源事实到界面

[snapshot_builder.py](../../packages/design-playbook/mcp/run_console/snapshot_builder.py) 读取既有权威，构建带来源的快照；[snapshot_v1.schema.json](../../packages/design-playbook/mcp/run_console/snapshot_v1.schema.json) 与 [contract.py](../../packages/design-playbook/mcp/run_console/contract.py) 约束输出。界面消费快照，不通过按钮直接改写验收结论。

`unknown`、冲突、缺失和来源变化是可见状态，不自动折算成成功。[source_registry.py](../../packages/design-playbook/mcp/run_console/source_registry.py) 定义可读取来源，[projection.py](../../packages/design-playbook/mcp/run_console/projection.py) 解析会话范围内的来源定位符并核对内容。源码变化后旧定位符不能继续当作当前证据。

## 启动与安全

[session.py](../../packages/design-playbook/mcp/run_console/session.py) 绑定一个显式 run，管理进程内会话；[http_server.py](../../packages/design-playbook/mcp/run_console/http_server.py) 按需在 loopback 提供服务。[run-status](../../packages/design-playbook/commands/run-status.md) 只呈报符合条件的 `open-console` 延续动作，不静默启动服务器。

浏览器请求须通过既有会话与请求安全检查。修改路由时复用 [request_security.py](../../packages/design-playbook/mcp/run_console/request_security.py)；不能为了方便本地调试扩大文件读取范围或绕开令牌。

## 写入与导出

有限动作由现有 allowlist 与状态裁决控制，不提供任意命令执行。Diagnostic export 先预览，再由参与者审阅确认后写入；[导出事务](../../packages/design-playbook/mcp/run_console/export_transaction.py) 重新核对候选与来源集合。接受导出契约不等于外部试用门已通过，见 [ADR-0044](../adr/0044-diagnostic-export-contract-v1.md)。

相关纯 Python 与浏览器测试在 [run_console tests](../../packages/design-playbook/tests/run_console/)。API 字段与动作库存直接查源文件，不在本文维护第二份生成表。
