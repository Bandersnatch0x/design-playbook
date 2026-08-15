# Craft audit (队列监控升级 — P3 全量档 dogfood)

Registry: `skills/design-playbook/references/rules.md`, full catalog (P3 run: 适用谓词全求值). Seven-column rows; applicability predicates evaluated per entry. 横切五条目同步求值（a11y/resp/perf applicable；i18n/sec not-applicable 附理由）。

| ID@ver | Applicability | Predicate reason / missing proof | Result | Rendered evidence | Source evidence | Exception check | Positive fix |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CRAFT-01@1 | applicable | - | clear | 主列表与控制台不并置第二主行动；全局暂停为控制台治理动作而非页面主行动 | 仅批量重试在操作条使用 primary 变体 | 单主行动符合场景 | - |
| CRAFT-02@1 | applicable | - | clear | 运行列表与 feed 均为可比较行式条目，未卡片化 | Table 承载行记录；feed 条目固定高度行式 | 可比较运维行不适用卡片例外 | - |
| CRAFT-03@1 | applicable | - | clear | 页面分区无框；仅对话框与抽屉有界 | 控制台/列表/侧区靠间距与字重分区 | 有界对话框是真实框工具 | - |
| CRAFT-04@1 | applicable | - | clear | 中性面主导；语义色仅状态命名（running/paused/failed） | 状态徽标使用独立语义令牌 | 无单色系例外诉求 | - |
| CRAFT-05@1 | applicable | - | clear | 控件几何各自特定；无泛化胶囊 | 按钮与徽标使用各自控件半径 | 无品牌几何例外诉求 | - |
| CRAFT-06@1 | applicable | - | clear | 紧凑控制台层级用结构与字重 | 控制台与主列表共用层级令牌，无 display 字号 | 无 hero 场景主张 | - |
| CRAFT-07@1 | applicable | - | clear | 全局暂停/恢复图标按钮带可访问名（R4 修复后） | evidence/L6.2-pause-trace.json a11y 复走查 | 破坏性动作（中止）保留显式文字 | - |
| CRAFT-08@1 | not-applicable | 本 run 表面无装饰动效（进度反馈用条目级进度文字与 busy 态，未引入动画） | - | - | - | 无动效面可查 | - |
| A11Y-01@1 | applicable | - | clear | 控制台 feed 条目与全局控制均有可访问名称与 role；暂停失败 toast role=alert | evidence/L6.2-pause-trace.json a11y 复走查（首轮缺口见 R4 finding，已闭合） | 无已声明豁免 | - |
| RESP-01@1 | applicable | - | clear | 声明视口 1280x800 下主路径与控制台跨页路径可用 | 响应式行为符合声明视口组 | 契约仅声明桌面视口 | - |
| I18N-01@1 | not-applicable | 单语控制台（zh-CN），无 i18n 声明（无 i18n.* 契约字段，L1 未声明多语言用户群） | - | - | - | 单语声明成立 | - |
| PERF-01@1 | applicable | - | clear | 长运行有持续进度感（feed 条目级进度逐 tick 更新；全局暂停 busy 即时反馈） | evidence/L6.2-pause-trace.json 反馈序列 | 反馈相称性未承诺耗时阈值（契约无阈值声明） | - |
| SEC-01@1 | not-applicable | 声明范围无敏感操作新增（敏感模拟参数默认脱敏沿用；全局暂停非敏感操作） | - | - | - | 无敏感面可查 | - |
