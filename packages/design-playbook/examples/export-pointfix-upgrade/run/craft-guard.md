# Craft audit (空数据集导出修复 + 列范围升档)

Registry: `skills/design-playbook/references/rules.md`. Seven-column rows; after the P2 escalation the full catalog is evaluated (over-compliance from the P1 subset is kept, not re-widened).

| ID@ver | Applicability | Predicate reason / missing proof | Result | Rendered evidence | Source evidence | Exception check | Positive fix |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CRAFT-01@1 | applicable | - | clear | 行选择工具条恰一主行动（批量导出） | 仅批量导出按钮使用 primary 变体 | 单主行动符合场景 | - |
| CRAFT-02@1 | applicable | - | clear | 列表为可比较表格而非等权卡片墙 | Table 承载行记录，无卡片包装 | 可比较运营行不适用卡片例外 | - |
| CRAFT-03@1 | applicable | - | clear | 页面分区无框；仅导出面板有界 | Dialog 独占弹层语义，无嵌套卡片 | 有界对话框是真实框工具 | - |
| CRAFT-04@1 | applicable | - | clear | 中性面主导；语义色仅状态命名 | 空数据集提示用状态令牌，非装饰色 | 无单色系例外诉求 | - |
| CRAFT-05@1 | applicable | - | clear | 控件几何各自特定；无泛化胶囊 | 按钮与复选框使用各自控件半径 | 无品牌几何例外诉求 | - |
| CRAFT-06@1 | applicable | - | clear | 紧凑控制台层级用结构与字重 | 面板内无 display 字号令牌 | 无 hero 场景主张 | - |
| CRAFT-07@1 | applicable | - | clear | 高频动作用图标按钮且有无障碍名 | 图标按钮带可访问标签 | 破坏性动作保留显式文字 | - |
| CRAFT-08@1 | not-applicable | 本 run 表面无动效（空数据集提示与列圈选用状态文字，未引入动画） | - | - | - | 无动效面可查 | - |
| A11Y-01@1 | applicable | - | clear | 超限 toast role=alert 与可读名称在位（上轮修复保持）；空数据集提示为文字 toast | toast 组件绑定 role 与名称 | 无已声明豁免 | - |
| RESP-01@1 | applicable | - | clear | 声明视口 1280x800 下主路径与空态防护可用 | 响应式行为符合声明视口组 | 契约仅声明桌面视口 | - |
| I18N-01@1 | not-applicable | 单语控制台，无 i18n 声明（无 i18n.* 契约字段，L1 未声明多语言用户群） | - | - | - | 单语声明成立 | - |
| PERF-01@1 | blocked | 性能感知需运行时度量，本 run provider 缺度量面（measurement 层不可采） | - | 导出等待仅观察到 busy 态 | 度量面缺席，无法判定反馈与耗时的相称性 | 无法在不承诺阈值的情况下检查例外 | 补采运行时度量后重评；缺口的证据语义见 point-back 覆盖声明 |
| SEC-01@1 | not-applicable | 声明范围无敏感操作新增（导出非敏感数据；隐藏敏感列由 column_scope 假设排除） | - | - | - | 无敏感面可查 | - |
