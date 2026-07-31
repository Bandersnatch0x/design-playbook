# craft-guard — 事件流监控页

**craft-guard**（步骤 8，对 filled-ui.html）

## CRAFT rows

- **CRAFT-01 加载层级**：初始骨架行（shimmer，tier 2）；无无界 spinner。
- **CRAFT-02 动效目的**：骨架 shimmer（加载反馈）；新事件行 .new 高亮 300ms（rowflash，感知提示）；`prefers-reduced-motion` 已加（shimmer + rowflash 关闭）。
- **CRAFT-03 层级**：h1 → 事件行（时间/徽章/来源/摘要基线对齐）→ 详情（弱化 muted）。关键级左侧警示条 + 徽章双编码。
- **CRAFT-04 CJK 排版**：`Microsoft YaHei / PingFang SC / Noto Sans CJK SC` 系统栈；无外部字体；13-13.5px 正文，等宽时间/来源列（mono 栈）。
- **CRAFT-05 焦点可见**：事件行 `:focus-visible` 描边；键盘展开（Enter/Space）；暂停按钮 aria-pressed 两态。
- **CRAFT-06 空态**：`?empty=1` → 「暂无事件」+ 刷新（非空白）。
- **CRAFT-07 密度/一致性**：console-tight 行高 42px；徽章色 + 文本双编码（色觉安全）；行距统一。
- **CRAFT-08 令牌**：全走 `var(--*)` 角色令牌；无裸 hex 于组件外；severity 三态角色令牌（crit/warn/info 各 bg+tx+bar）。

## Findings → ui-evaluator

- 无（本页 craft 检查全过；模拟流 demo 数据已注「（demo）」标记）
