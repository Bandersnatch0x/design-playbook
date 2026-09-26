# 产品方向与验收边界

更新于 2026-09-24。本文说明长期产品方向和验收边界，不承载个人排期、实施计划或工作票。

## 当前阶段

design-playbook 为 coding agent 提供带证据的 UI 交付链路：声明、契约、实现、验收、回流。
首要使用场景是在已有 Web 产品中修改 UI，帮助执行者理解目标、定位阻塞、修复问题并验证结果。
它不是独立托管应用，也不承诺通用设计平台或组织协作工作台。

项目处于维护者自用和维护阶段。catalog 提交、招募和外部试验暂停；
新增能力必须取得 [ADR-0045](adr/0045-external-evidence-spend-gate.md) 所要求的明确、有界授权。
安装路径继续可用，渠道恢复、日期到达或提案写成均不自动解冻。
内部自用记录、演示和自动化夹具不能冒充使用者反馈或满足外部验收门。

本地可核验的正式发布基线为 `v0.25.2`，见[发布记录](releases/v0.25.2.md)；
本文未重新查询 npm 或 catalog 的远端状态。源码中的后续修复不能倒算进已发布版本。

## 已有能力与限制

当前能力及使用入口以 [README](../README.md)、[产品定义](../PRODUCT.md) 和
[领域上下文](../CONTEXT.md) 为准：

- Design I/O 管线将 Criteria、Evidence、Findings 和 point-back 关联起来，支持有界修复回流。
- 可选 Preview / Evidence runtime 提供人工确认与证据采集；采集者不拥有验收裁决权。
- Run status、handoff、review 和 Repair Packet 提供继续工作所需的来源与下一责任人。
- Run Console 提供本地、单 run、loopback 会话视图；快照是来源投影，不是新的状态权威。
  已有 refresh、source view、copy 及经 [ADR-0044](adr/0044-diagnostic-export-contract-v1.md)
  单独接受的 Diagnostic export。
- Console 仍为 **local / experimental / trial-gated**。
  `G-RO-TRIAL-PASS` 未满足；Role attestation 仍未解锁。
  已交付的导出工具不等于已经取得真实试验证据。

## 维护方向

优先修复能在真实自用中重现的问题：重复补充上下文、定位失败依据耗时、修复交接遗漏、
证据与判据无法对应、文档和运行行为不一致。新增功能提案与测量计划保留本地，
公开交付应说明实际解决的痛点、可观察验收结果及剩余限制，不以功能数量代替效果。

长期希望验证的结果是：执行者在 60 秒内理解目标、来源裁决、阻塞来源和下一责任人，
完成 `Recirculate → repair → Pass`，并主动在另一项真实 UI 工作中再次使用。
当前没有证据证明这一结果已达到；不能把它写成产品现状。

## 权威与安全

| 角色 | 拥有 | 不能代替 |
| --- | --- | --- |
| 人工 Semantic approver | 意图、长期决策、规则提升、例外和角色范围内的语义确认 | 可复现的机器事实 |
| 确定性 validator | hash、绑定、结构门禁和可复现指标 | 产品或设计意图判断 |
| Agent | 提案、实现、修复建议和学习候选 | 人工最终确认或自我提升 |
| Runtime Provider | 采集 Artifacts | Evidence 绑定、Findings 或 verdict |

沿用 `execute_capture_plan` 作为 Provider 采集入口。投影和 typed actions
不能建立可写的 `DesignRun` 权威、任意文件写接口或第二套裁决来源，
见 [ADR-0035](adr/0035-run-view-projection-authority.md)。

需要特定角色判断的 claim 才要求相应确认，不设置全局三角色门。
Role attestation 只限定确认范围，不证明身份、雇佣关系或法律同意；
继续 run 不意味着代其他角色批准。

Console 会话只绑定一个显式选定的 run，不是 daemon、跨 run 仪表盘或云服务。
快照重建须保持来源 hash 一致；`known`、`unknown`、`stale`、`inconsistent`
不得混为一个状态，也不能静默显示旧成功结果。

Loopback 不是信任边界。会话 token、Origin 校验、只读 GET/HEAD、固定 action schema、
Source locator containment 和 fail-closed 规则仍适用。
Console 不执行修复、不自动重跑 Agent、不写验收；
新增 action 必须明确既有 owner，见
[ADR-0037](adr/0037-local-single-run-console-lifecycle.md) 和
[ADR-0038](adr/0038-run-snapshot-contract-and-loopback-security.md)。

## 外部验证契约

本节保留暂停前确立的长期验收定义，不是招募计划或恢复授权。
实际执行还须单独授权，并遵循[只读试验协议](agents/run-console-read-only-trial.md)。

### 范围与计数

外部验证限于已有 Web 产品的 P2/P3 修改，启用 Evaluator，且至少一项渲染或交互
Criterion 有 Manifest 绑定的 Artifact。Greenfield、营销站生成、原生移动/桌面、
跨平台自动化和 Canvas 不在该范围。

- **Qualified audited run**：符合上述范围，有最终 point-back，披露全部维护者干预。
- **Voluntary repeat**：参与者在首次 run 结束后，自主为另一项真实 UI 工作开启新的合格 run。
  同 run 修复、重开 Console、重复导出或维护者安排的演示均不计。
- 理解度检查固定测量意图、来源裁决、阻塞来源、下一责任人。
  满意度或访谈不能替代这四项来源绑定答案。

### 隐私

无隐式遥测、账号要求、机器指纹或上传端点。参与者显式发起并检查导出，
之后自行选择手动分享。导出仅为版本化 JSON 与 Markdown，
保存在该 run 的 `trial-export/`，不是 Evidence 或验收输入。
不包含密钥、凭证、源码、未选择的工件或原始模型推理。
导出之外的计时和回答由获授权的人工观察并记录，
见 [ADR-0036](adr/0036-invited-trial-data-and-role-boundary.md)。

### 最低验收线

以下门槛全部保留，不因自用或文档迁移降低：

- 至少 5 名无关联外部参与者、3 个真实仓库、10 次 Qualified audited runs。
- 至少 5 次完整 `Recirculate → repair → Pass`。
- 至少 3/5 参与者在 30 天内完成 Voluntary repeat。
- 至少 80% 的 run 无需维护者手改工件即可形成完整 Evidence 闭环。
- 至少 4/5 参与者不打开原始 run 文件即可正确回答四项理解度问题，中位定位时间小于 60 秒。
- 真实阻塞 Findings 中，被判为不可操作、错误或不能指回声明 owner 的比例小于 20%。

公开 beta 还要求：零竞争写入、零未解释敏感数据披露、连续 50 次快照重建无语义漂移，
且 parity、containment、action-owner 和安全门全部通过。时间流逝不能代替验收。

### 停止条件

- 合格邀请开始后第 45 天，首次成功的使用者不足 3 人：暂停 Console 扩展，先修定位、安装或闭环质量。
- Voluntary repeat 低于 40%：不启动通用跨 run Design Memory。
- 视图未显著改善理解或定位时间：停止组织工作台方向，保留 CLI 状态摘要。
- 不可操作、错误或不能回指的阻塞 Findings 超过 20%：先修 Criterion/Evidence 语义，
  暂停 Memory 与多 Agent 扩展。
- 违反权威边界、产生竞争写入或安全门未过：停止推进，先修契约或实现。

ADR-0044 的 30 天检查点约为 2026-10-22，原 Day-90 复议约为 2026-11-23。
这是复议时点而非交付承诺；无外部证据可以得到停止结论，任何恢复仍需明确裁决。

## 非目标与变更规则

当前不开展通用 Design Memory、多 Agent runtime、Canvas、持久仪表盘、云或组织 Workspace、
企业身份治理、隐式遥测、自动接受，以及新的公共 adapter 扩张。
Adapter 矩阵保持 [ADR-0042](adr/0042-multi-platform-adapter-generator.md) 修订规定的 30 行。
不因借鉴外部工具而引入产品依赖；核心契约保持工具与技术栈中立。

跨 run 学习需重复使用与真实需求证据；协调器需可复现的多 writer 冲突及回放/回滚证明；
远程能力需身份、权限、同意、保留和删除决策。它们都不是已承诺功能。
新的 writer、远端表面、身份声明或权威迁移必须先有明确决策。
具体已接受 ADR 优先于本文概述，领域词汇以 `CONTEXT.md` 为准。
