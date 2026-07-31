# craft-guard — 塔罗牌浮雕显示页

**craft-guard**（步骤 8，对 filled-ui.html）

## CRAFT rows

- **CRAFT-01 加载层级**：初始渲染用骨架卡形（shimmer，tier 2——非阻塞交互占位）；洗牌动画期间按钮禁用（tier 2）。无无界 spinner。
- **CRAFT-02 动效目的**：翻牌 rotateY .6s（状态揭示，有目的）；洗牌 .65s 重排（状态变化）；骨架 shimmer（加载反馈）。无装饰性循环动效。`prefers-reduced-motion` 已加（reduce 下关闭 rotateY/shuffle/shimmer）。
- **CRAFT-03 层级**：h1（页题）→ 卡名（浮雕字）→ 牌意（lightbox 内）。卡名 21px / 光盒 26px，层级清晰。计数徽章为 status 角色（非层级竞争者）。
- **CRAFT-04 CJK 排版**：正文 `Songti SC / STSong / Noto Serif CJK SC` 系统宋体栈 + fallback serif；无外部字体依赖；行高 1.7（lightbox 牌意）；字距 0.16-0.22em 用于标题。无乱码风险（UTF-8 + CJK 栈）。
- **CRAFT-05 焦点可见**：卡组件 `:focus-visible` gold 描边 + 3px offset；按钮同。键盘可翻（Enter/Space）、Esc 关光盒。
- **CRAFT-06 空态**：`?empty=1` 触发「牌库为空」+ 重载按钮（非空白）。
- **CRAFT-07 阴影/浮雕层次**：多层 inset 高光/阴影（emboss），卡背 lattice + ☽，卡面 3 层 inset + 外投影。风险：浏览器浮雕渲染差异（decision-report risks 已记）。
- **CRAFT-08 令牌**：颜色全走 `var(--*)` 角色令牌（bg/panel/line/paper/ink/gold 族）；无裸 hex 于组件样式外；font-family 令牌。gaps: 无未记令牌。

## Findings → ui-evaluator

- reduced-motion 支持缺失（source: craft，low）
- 浮雕渲染跨浏览器差异风险（source: craft/design，med，已入 decision-report risks）
