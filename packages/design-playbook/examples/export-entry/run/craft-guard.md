# Craft audit (数据导出入口)

Registry: `skills/design-playbook/references/rules.md`, full catalog (P2 run). Seven-column rows; applicability predicates evaluated per entry.

| ID@ver | Applicability | Predicate reason / missing proof | Result | Rendered evidence | Source evidence | Exception check | Positive fix |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CRAFT-01@1 | applicable | - | clear | 行选择工具条恰一主行动（批量导出） | 仅批量导出按钮使用 primary 变体 | 单主行动符合场景 | - |
| CRAFT-02@1 | applicable | - | clear | 列表为可比较表格而非等权卡片墙 | Table 承载行记录，无卡片包装 | 可比较运营行不适用卡片例外 | - |
| CRAFT-03@1 | applicable | - | clear | 页面分区无框；仅导出面板有界 | Dialog 独占弹层语义，无嵌套卡片 | 有界对话框是真实框工具 | - |
| CRAFT-04@1 | applicable | - | clear | 中性面主导；语义色仅状态命名 | 语义令牌独立映射警告与失败 | 无单色系例外诉求 | - |
| CRAFT-05@1 | applicable | - | clear | 控件几何各自特定；无泛化胶囊 | 按钮与复选框使用各自控件半径 | 无品牌几何例外诉求 | - |
| CRAFT-06@1 | applicable | - | clear | 紧凑控制台层级用结构与字重 | 面板内无 display 字号令牌 | 无 hero 场景主张 | - |
| CRAFT-07@1 | applicable | - | clear | 高频动作用图标按钮且有无障碍名 | 图标按钮带可访问标签 | 破坏性动作保留显式文字 | - |
| CRAFT-08@1 | not-applicable | 本 run 表面无动效（导出反馈用状态文字与 busy 态，未引入动画） | - | - | - | 无动效面可查 | - |
| A11Y-01@1 | applicable | - | hit | 超限 toast 节点无可访问名称与 role | toast 组件未绑定 role=alert 与名称 | 无已声明豁免 | toast 增加 role=alert 与可读名称（含超限数值）；组件语义入 components 声明 |
| RESP-01@1 | applicable | - | clear | 声明视口 1280x800 下主路径可用 | 响应式行为符合声明视口组 | 契约仅声明桌面视口 | - |
| I18N-01@1 | not-applicable | 单语控制台，无 i18n 声明（无 i18n.* 契约字段，L1 未声明多语言用户群） | - | - | - | 单语声明成立 | - |
| PERF-01@1 | blocked | 性能感知需运行时度量，本 run provider 缺度量面（measurement 层不可采） | - | 导出等待仅观察到 busy 态 | 度量面缺席，无法判定反馈与耗时的相称性 | 无法在不承诺阈值的情况下检查例外 | 补采运行时度量后重评；缺口的证据语义见 point-back 覆盖声明 |
| SEC-01@1 | not-applicable | 声明范围无敏感操作新增（导出非敏感数据；隐藏敏感列由 column_scope 假设排除） | - | - | - | 无敏感面可查 | - |
| COPY-01@1 | blocked | 条目 2026-08-28 注册，晚于本 run 存档（2026-08-14）；主动语态与动作命名一致性审查所需的全流程文案清单未采集 | - | - | - | - | - |
| COPY-02@1 | blocked | 条目 2026-08-28 注册，晚于本 run 存档；用户侧命名审查所需的界面名词与实现命名对照未采集 | - | - | - | - | - |
| COPY-03@1 | blocked | 条目 2026-08-28 注册，晚于本 run 存档；错误信息语气审查所需的错误态文案样本未采集 | - | - | - | - | - |
| A11Y-02@1 | blocked | 条目 2026-08-28 注册，晚于本 run 存档；可见键盘焦点判定所需的聚焦态截图与键盘走查未采集（a11y 树无法证明视觉属性） | - | - | - | - | - |
| CRAFT-09@1 | blocked | 条目 2026-08-28 注册，晚于本 run 存档；选择器优先级冲突审查所需的样式源走查未执行 | - | - | - | - | - |
| CRAFT-10@1 | blocked | 条目 2026-08-28 注册，晚于本 run 存档；结构装置与内容属性对应关系的走查未执行 | - | - | - | - | - |
| DECIDE-01@1 | blocked | 条目 2026-08-28 注册，晚于本 run 存档；DD-0002（compare 档）理由中无 anti-default 自检答案可回溯 | - | - | - | - | - |

注：2026-08-28 注册批（COPY-01/02/03、A11Y-02、CRAFT-09/10、DECIDE-01）晚于本 run 存档；按三态谓词补记，blocked 行在理由列记缺失证据面。
