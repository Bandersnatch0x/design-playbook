# Craft audit (导出升级 — P3 全量档)

Registry: `skills/design-playbook/references/rules.md`, full catalog (P3 run: 适用谓词全求值). Seven-column rows; applicability predicates evaluated per entry. 横切五条目同步求值（a11y/resp/perf applicable；i18n/sec not-applicable 附理由）。

| ID@ver | Applicability | Predicate reason / missing proof | Result | Rendered evidence | Source evidence | Exception check | Positive fix |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CRAFT-01@1 | applicable | - | clear | 主列表恰一主行动（批量导出）；全局状态区不争夺主行动 | 仅批量导出按钮使用 primary 变体 | 单主行动符合场景 | - |
| CRAFT-02@1 | applicable | - | clear | 任务 feed 为固定高度条目列表，未卡片化 | Table 承载行记录；feed 条目为行式 | 可比较运营行不适用卡片例外 | - |
| CRAFT-03@1 | applicable | - | clear | 页面分区无框；仅导出对话框有界 | Dialog 独占弹层语义，无嵌套容器 | 有界对话框是真实框工具 | - |
| CRAFT-04@1 | applicable | - | clear | 中性面主导；语义色仅状态命名 | 进行中/完成/错误态使用独立语义令牌 | 无单色系例外诉求 | - |
| CRAFT-05@1 | applicable | - | clear | 控件几何各自特定；无泛化胶囊 | 按钮与状态条目使用各自控件半径 | 无品牌几何例外诉求 | - |
| CRAFT-06@1 | applicable | - | clear | 紧凑控制台层级用结构与字重 | 状态区与主列表共用层级令牌，无 display 字号 | 无 hero 场景主张 | - |
| CRAFT-07@1 | applicable | - | clear | 高频动作（打开结果入口）图标按钮且有无障碍名 | 完成态条目入口带可访问标签 | 破坏性动作保留显式文字 | - |
| CRAFT-08@1 | not-applicable | 本 run 表面无动效（进度反馈用条目级进度文字与 busy 态，未引入动画） | - | - | - | 无动效面可查 | - |
| A11Y-01@1 | applicable | - | clear | 状态区条目与结果入口均有可访问名称与 role；toast 沿用 r2 修复（role=alert + 可读名） | a11y 走查证据 evidence/L6.2-return-trace.json | 无已声明豁免 | - |
| RESP-01@1 | applicable | - | clear | 声明视口 1280x800 下主路径与状态区跨页路径可用 | 响应式行为符合声明视口组 | 契约仅声明桌面视口 | - |
| I18N-01@1 | not-applicable | 单语控制台，无 i18n 声明（无 i18n.* 契约字段，L1 未声明多语言用户群） | - | - | - | 单语声明成立 | - |
| PERF-01@1 | applicable | - | clear | 长导出有持续进度感（30s 窗口 5 次采样，条目级进度持续更新） | evidence/L6.1-status-trace.json 进度采样序列 | 反馈相称性未承诺耗时阈值（契约无阈值声明） | - |
| SEC-01@1 | not-applicable | 声明范围无敏感操作新增（导出非敏感数据；隐藏敏感列由 column_scope 假设排除） | - | - | - | 无敏感面可查 | - |
