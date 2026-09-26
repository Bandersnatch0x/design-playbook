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

## 前端改动的只读摘要

源码工作区的 `run-status --scope` 提供有界自用摘要，复用现有声明解析、证据校验、快照及 Repair Packet。这是 CLI 读视图，不是新增 Console 面板，也不修改 Snapshot v1。当前没有实测提效或已发布版本承诺。

```text
python packages/design-playbook/scripts/run_status.py <run> --scope path:P1 --scope page:checkout --json
```

- 必须显式指定 run。L3 路径、L6 路径引用和 L2 页面精确声明支持可追溯关联；组件、文件或自然语言推测没有可靠声明关联时保持 `unknown`，不等于“无影响”。可选 Git 线索必须明确根目录和比较基线，不扫描源码。
- L6 的明确取证声明决定 proof、状态和视口，无法解析时不猜测。L5 只枚举已声明的非空状态格；采样 `reported` 不代表绑定已验证。识别格式及参数见 [run-status 命令说明](../../packages/design-playbook/commands/run-status.md)。
- 来源状态、绑定完整性和 evaluator 结果分别展示。缺必需证据为 `blocked`，跳过 evaluator 保留 `unaudited`；N/A 与未审查理由保留来源引用，不复制可能含私密信息的原文。不访问登录态、不启动 Provider、不写 Manifest、不替代人工批准。
- 复验候选保留原 owner 的失效集、恢复阶段和重新取证要求。声明关联不能证明代码影响已穷尽，因此始终提示不能安全缩小原复验范围，不自动执行建议。
- 再用同一输入及 `--expected-source-hash sha256:<上次哈希>` 核对来源后，才能使用当次返回的 owner 命令。来源变化或 owner 未完成来源核验时标为 `stale` 并移除可复制命令；这不是文件锁，之后再修改仍需刷新。

摘要包含本地 scope 名称及相对文件名，应按项目隐私要求使用。命令退出 0 仅表示生成了摘要，不是验收 Pass。

相关纯 Python 与浏览器测试在 [run_console tests](../../packages/design-playbook/tests/run_console/)。API 字段与动作库存直接查源文件，不在本文维护第二份生成表。
