# Point-back findings — 事件流监控页

Produced by **ui-evaluator** after Design I/O (ux-spec → plan → ui-picker → preview* → fill → craft-guard → observe* → eval)。Run root: .scratch/design-playbook-v0/dogfood/2026-08-01-event-stream/

## Evidence ledger (L6)

criterion: L6.1
required: 首屏渲染事件列表（时间戳/级别徽章/来源/摘要，非空白）；证据 = 首屏截图
observed: evidence/L6.1-ready.png
note: provider 捕获（observed_state=ready）；surface: live（http.server）
result: pass

criterion: L6.2
required: 关键级有警示条 + 徽章（色+文本双编码），与 info 可区分；证据 = 列表截图
observed: playwright 复验：.event.critical box-shadow inset rgb(224,82,82) 3px；徽章「关键」bg rgb(90,30,30) ≠ info 徽章 bg
result: pass

criterion: L6.3
required: 点击行展开内联详情，再点收起；证据 = 交互 trace
observed: evidence/L6.3-detail.zip
note: provider interaction trace（click .event.critical）
result: pass

criterion: L6.4
required: 点击暂停 → 计数停增且按钮「恢复」，再点恢复继续；证据 = 交互 trace
observed: evidence/L6.4-pause.zip
note: provider interaction trace（click #pause）；aria-pressed 两态切换（源码核验）
result: pass

criterion: L6.5
required: 选择「关键」→ 仅关键事件可见且计数联动；证据 = 交互 trace
observed: playwright 复验：filter critical → 列表 2 关键 / 0 非关键
result: pass

criterion: L6.6
required: 每行/按钮/徽章有可访问名，暂停按钮 pressed 态；证据 = a11y 树
observed: evidence/L6.6-a11y.json
note: provider a11y capture；radiogroup/radio/status 语义（源码核验 aria-pressed/aria-checked）
result: pass

criterion: L6.7
required: 空态显示「暂无事件」非空白；证据 = 状态截图
observed: playwright 复验：?empty=1 → 「暂无事件 事件源未连接；请刷新重试」+ 刷新按钮
result: pass

## Findings

- issue: 模拟流事件数据（deploy/disk/redis 等）为 demo 占位，非真实数据源
  source: spec（L1 非目标已声明无后端；演示数据）
  fix: 产品集成时接真实事件源；页面契约（列表/徽章/筛选/暂停）不受影响
  severity: low
- issue: 事件追加无进入动画（监控页密度优先，CRAFT-02 有意为之），新事件视觉提示仅靠位置
  source: craft
  fix: 可选：新事件行短暂高亮（300ms）增强感知，不影响 reduced-motion
  severity: low

## Verdict

Pass

七条 L6 全 pass（4 条 provider 捕获 + 3 条 playwright 复验）；零 blocking；preview* 真实 HITL（Playwright 点击）确认 floor_pass=true，G5 满足；两项 low finding 点回 spec/craft 声明层，非阻断。
