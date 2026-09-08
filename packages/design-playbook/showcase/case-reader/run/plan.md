<!-- run-profile: v1 -->

```yaml
tier: P2
criteria:
  - intent: build
  - consequence: feature
  - durable-artifacts: requested
  - shaping: full S0-S6 with actual user confirmation
  - decision-tier: R/C within confirmed single-page read-only scope
confirmed_by: user + 2026-09-08T10:11:31+08:00 (shaping/confirm-round-1.json)
skipped:
  - design-baseline: new standalone UI, router requires_baseline=false; no existing baseline waived
  - reference-intake: first-party source data only, router requires_reference_contract=false
  - native-craft: browser surface, no native OS chrome
upgrades: []
```

# 案例阅读器 — 本次实现计划

fill: ../index.html

## 范围与描述映射

- 用户要求补充完整实跑 → 新建实际可用的案例原文阅读器，完整记录本次生成、确认、测试、捕获、验收和交付过程。
- spec L1 / L2：读者按旅程查阅原文、来源和限制；CP-A/B/C 已由真实 Preview 事务确认，不能当作实现通过。
- L6.1 / L6.5：从已有仓库文件构建内嵌文档，文本逐项校验，HTML 标记不执行，无外部请求。
- L6.2 / L6.3 / L6.4：过滤、深链接与恢复、键盘焦点和响应式布局，各自留独立可失败检查。

## 设计输入

- 新的只读浏览器工具，没有可复用的组件库；使用平台原生链接、搜索和文档语义。
- 范围确认反馈“字体大一点”，采用 18px 正文；原始“背景高太尉浅绿色”解释为浅绿色背景，在下一次真实设计预览中请用户核对，不改写反馈原文。
- 保留目录的旅程上下文，不以卡片墙、模拟业务按钮或装饰统计替代案例内容。

## 执行与接续

- 先确认设计；Fill 独立按规格和决策编写，不复制 preview HTML。
- 工艺全目录检查；Provider 在实际 Fill 上捕获三视口、无结果与错误状态、a11y 与交互轨迹，按每次返回立即绑定 manifest。
- 真实暂停点：设计确认后、Fill 前执行独立 run-status 进程，保留当前阻塞与下一动作；恢复时只读 run 文件重建上下文。
- 无真实缺陷不人为制造回流。若发现缺陷，保留测试失败 / 发现与定点修复后的证据，不降低标准。
- 验收为当前 agent 的声明驱动评审，不声称独立专家评审、设备实验室或外部用户试用。随后执行真实 run-handoff 并在交付副本复跑同一用户路径。
