# craft-guard — 系统设置页

**craft-guard**（步骤 8，对 filled-ui.html）

## CRAFT rows

- **CRAFT-01 加载层级**：初始骨架行（shimmer，tier 2）；保存中按钮禁用（tier 2）。
- **CRAFT-02 动效目的**：开关 thumb 滑动 .18s（状态反馈，有目的）；深色背景 .25s 过渡（主题切换反馈）；骨架 shimmer；`prefers-reduced-motion` 已加（全关闭）。
- **CRAFT-03 层级**：h1 → 分组标题（muted 小字）→ 行 label（14px）→ helper（12px muted）；主操作保存按钮实底高对比。
- **CRAFT-04 CJK 排版**：`Microsoft YaHei / PingFang SC / Noto Sans CJK SC` 系统栈；无外部字体；12-14px 层级分明。
- **CRAFT-05 焦点可见**：switch `:focus-visible` 描边；键盘 Space/Enter 切换；select/按钮焦点可见。
- **CRAFT-06 空态**：`?empty=1` → 「暂无设置项」+ 重载（非空白）。
- **CRAFT-07 一致性**：三开关同一 switch 组件语义；分组边框圆角一致；深浅两主题令牌一致。
- **CRAFT-08 令牌**：全走 `var(--*)` 角色令牌；深浅主题同令牌集换值（无硬编码双主题色）。

## Findings → ui-evaluator

- 重置已改自绘 `<dialog>` 确认弹层（主题令牌 + showModal + Esc/取消/恢复默认；CRAFT-02 reduced-motion 兼容）
