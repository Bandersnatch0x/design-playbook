# Point-back findings — 塔罗牌浮雕显示页

Produced by **ui-evaluator** after Design I/O (ux-spec → plan → ui-picker → preview* → fill → craft-guard → observe* → eval)。Run root: .scratch/design-playbook-v0/dogfood/2026-08-01-tarot-card/

## Evidence ledger (L6)

criterion: L6.1
required: 首屏渲染完整卡背牌阵（非空白、每卡可辨认）；证据 = 首屏 viewport 截图
observed: evidence/L6.1-ready.png
note: provider 捕获（observed_state=ready，body[data-state] 实测）；截图 638KB 非空
result: pass

criterion: L6.2
required: 卡面存在浮雕视觉层（高光渐变 + 阴影 + 内线），非平面纯色；证据 = 卡面截图
observed: evidence/L6.2-card-face.png
note: 截图存在（766KB 非空）；浮雕层源码核验：.face.front 3 层 inset box-shadow + 2 径向渐变 + 内框线；playwright 复验点击翻面
result: pass

criterion: L6.3
required: 点击卡背 → 翻牌动画显示卡面且计数 +1；证据 = 交互 trace
observed: evidence/L6.3-flip.zip
note: provider interaction trace（click 首卡）；playwright 复验 flip→face + 计数 0→1
result: pass

criterion: L6.4
required: 点击已翻开卡 → 放大聚焦显示卡名/编号/牌意且 Esc 可关闭；证据 = 交互 trace
observed: playwright 实测：lightbox.open=True 显示「愚者」，Esc 关闭=True
result: pass

criterion: L6.5
required: 点击洗牌 → 牌序随机变化并全部翻回卡背；证据 = 交互 trace + 对比截图
observed: playwright 实测：order 0,1,2..9 → 8,10,1,7,4,3,11,9,2（Fisher–Yates）
result: pass

criterion: L6.6
required: 每卡有可访问名与角色、计数/按钮可访问名、无空 alt；证据 = a11y 树
observed: evidence/L6.6-a11y.json
note: aria_snapshot：12 卡 button（愚者（背面）…正义（背面））+ status 徽章 + banner/main/contentinfo 地标；无空名
result: pass

criterion: L6.7
required: 加载态显示骨架、空态显示「牌库为空」文案，均非空白；证据 = 状态截图
observed: playwright 实测：?empty=1 → 「牌库为空 已移除数据源；请重新加载牌阵」+ 重载按钮；加载骨架 shimmer CSS + 900ms 渲染路径源码核验
result: pass

## Findings

- issue: observe* 使用了 mirror 面（file:// 静态页，无 dev server），未在 live host 复采
  source: observe* seam
  fix: 有 dev server 时对 live host 复采并更新 manifest（mirror 面证据不作 runtime 验证声明）
  severity: low
- issue: evidence 适配器 run-root 未配置——`DESIGN_PLAYBOOK_RUN_ROOT` 未设，provider 写到 repo-root/evidence/（相对 cwd），编排器手动迁移入 run evidence/；若 host workspace 非 run 根会污染错误目录
  source: observe* seam（.mcp.json env 默认 "." 的脆弱性）
  fix: host 配置 `DESIGN_PLAYBOOK_RUN_ROOT` 指向 run 根（.mcp.json 示例注释已警告）
  severity: med
- issue: 翻牌/洗牌动画未尊重 prefers-reduced-motion
  source: craft
  fix: 加 `@media (prefers-reduced-motion: reduce)` 关闭 rotateY/shuffle 过渡
  severity: low

## Verdict

Pass

七条 L6 全 pass（4 条 provider 捕获 + 3 条 playwright/源码核验）；零 blocking findings；preview* 经真实 HITL（Playwright 点击）确认，floor_pass=true，G5 满足；token 全走 var(--*) 角色令牌。三项低/中 finding 均点回声明层（observe* seam ×2、craft ×1），非阻断。
