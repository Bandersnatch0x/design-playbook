# 当前画布能力矩阵 — preview canvas capability matrix

> Effort：`canvas-upgrade`（评估把 preview canvas 升级到 Figma/Stitch 级别 + 本地版本控制）
> 票：`issues/01-current-canvas-matrix.md`
> 定位：**现有"画布"不是可视化编辑器，是 G5 人工确认门的 floating 批注覆盖层**（floating pill + drawer + 浮动气泡），渲染在受信任 parent 页面，原型被隔离在 sandboxed iframe（opaque origin）内。
> 约束：本矩阵为 effort 内部资产，只读盘点；行号基于 2026-08-07 读取的源文件。

## 0. 当前形态（一句话基线）

`preview_prototype` MCP 工具（stdio）→ 本地 HTTP 服务器 → 打开居中 Chromium app 窗口（1100×780）→ 渲染受信任 parent 页面：control bar（pill/drawer）+ 内嵌 `iframe sandbox="allow-scripts" srcdoc` 承载原型。用户 pin 元素 → 写 per-anchor 评论 + 整体 feedback → POST `/decide`（带一次性 token）→ transaction 层原子落盘 `decision-round-N.json` / `confirm-round-N.json` / `log.md`。

---

## 1. 交互维度

| 能力 | 当前实现 | 来源文件:行号 | 备注 |
| --- | --- | --- | --- |
| 元素选择（pin / 锚点，同源） | 有。pin 模式开启后 click 捕获，用 `cssPath()` 生成 DOM 路径 selector，锚定 hover 元素（非点击内层节点），push 进 `anchors[]` 并加 `.dpb-pin-target` 高亮 | control.js:512-547 | 选择器为 cssPath（id 快路径 + class + `:nth-of-type`，深度 ≤8），非 x/y 坐标 |
| 元素选择（跨源 iframe 内） | 部分。parent 无法看到 iframe 内 click / DOM；靠注入 iframe 的 BRIDGE_SCRIPT 捕获 click/hover、算好 cssPath 后 `postMessage({dpbPinAnchor:{selector,tag}})` 回 parent；parent 仅记录，`el=null` | browser.py:452-534, control.js:556-580 | 桥只发数据、不读 parent DOM/token（G5 安全契约，test_browser_control.py:600-624 锁定） |
| 选择 hover 高亮 | 有。`mousemove`（capture）给候选元素加 `.dpb-pin-hover`（虚线 outline） | control.js:494-510, control.css:445-448 | pin 关闭时跳过；control bar/spacer/float-root 内不算候选（control.js:497-499） |
| 批注（整体 feedback） | 有。drawer 内 `textarea[name=feedback]` 整体意见 | control.html:50-52 | 空反馈由 ADR-0008 floor 拦下（前端 mirror + 服务端权威） |
| 批注（per-anchor comment） | 有。每个 anchor 行一个 textarea（`input[data-i]`），输入即写回 `anchors[i].comment` 并同步浮动气泡 | control.html:208, control.js:582-591 | 浮动气泡仅在 comment 非空时显示（control.js:171） |
| 批注（浮动气泡显示） | 有。`.dpb-float-note` 气泡定位到目标元素（getBoundingClientRect + scroll 偏移），overflow 右移时翻转到左侧 | control.js:135-153, control.css:405-437 | z-index 999 < control bar 1000，避免遮住确认控件（control.css:401-404） |
| 锚点定位（locate） | 有。点 anchor 行 label → `scrollIntoView` + `.dpb-pin-flash` 闪烁动画 | control.js:593-608, control.css:449-457 | 跨源 anchor（el=null）无定位能力，代码已容忍 |
| 锚点删除 | 有。每行 remove 按钮 → 移除高亮/气泡/数组项 | control.js:609-620 | 无批量删除 |
| 锚点去重 | 有。同 selector 再次 pin 只更新 el 引用不新增 | control.js:524-532 | selector 即唯一键 |
| 拖拽（drag） | 无。无任何 drag/pointer 变换逻辑 | —（control.js 全文无 drag） | 整个 surface 是 overlay，不含可视化编辑 |
| 缩放 / resize / 改色 / 文本编辑 | 无。无 transform/resize/color/text 编辑 | — | 批注文本编辑是唯一"编辑" |
| 框选（marquee） | 无。无选择矩形逻辑 | — | 每元素逐一 pin |
| 多选 | 无。anchors 是单元素逐一追加的列表，无 shift/框选多选 | control.js:524-532 | 去重还限制了同 selector 多次选择 |
| 撤销 / 重做 | 无。无 history 栈；remove/clear 不可撤销 | — | draft（control.html:59, control.js:389-392）只保留不提交，不是 undo |
| draft（保留草稿暂不决定） | 有。关闭 drawer 不提交，feedback/anchors 留在表单中 | control.html:59, control.js:389-392 | 页面不刷新则表单内容保留 |
| 定位 pin 开关 | 有。drawer 内 toggle + 直接点"批注"按钮自动开 pin | control.html:33-35, control.js:301-310, 340-343 | ESC / 关闭 drawer 时自动退出 pin（control.js:475, 332） |

## 2. 渲染能力

| 能力 | 当前实现 | 来源文件:行号 | 备注 |
| --- | --- | --- | --- |
| DOM 现状（control 层） | 有。注入 `<style>` + control HTML + `<script>` 到 parent 页面 body，pill/drawer 用 `position:fixed` | control.py:154-159, control.css:66-78, 175-191 | 资源按需从同目录 `control.{html,css,js}` 读取（control.py:20-31） |
| 原型渲染 | iframe。`<iframe class="dpb-proto-frame" sandbox="allow-scripts" srcdoc="...">`，`position:fixed; inset:0; width/height:100%` | browser.py:565-580（iframe 576-578；样式 572-573） | 原型整体 html.escape 后塞进 srcdoc 属性（browser.py:555-562） |
| 跨源支持 | 部分。iframe 是 opaque origin（**故意不含** `allow-same-origin`），原型脚本够不到 parent DOM/token；跨源只能走 postMessage 桥 | browser.py:576-578, control.js:556-580 | G5 trust boundary；桥是 sandbox 化后的回归修复（browser.py:430-451） |
| 视觉缩放（zoom） | 无。无 zoom/pan 控制；iframe 固定 100% 视口 | browser.py:572-573 | 原型自身响应式由原型 HTML 决定（如 showcase round HTML 有 viewport meta，round-1.html:5） |
| 画布坐标系 | 无统一画布坐标。anchor 用 cssPath DOM 路径表达；浮动气泡用 viewport 坐标（getBoundingClientRect + scrollX/Y）定位 | control.js:73-107（cssPath）、135-153（定位） | 无 canvas/SVG/AST 坐标系；选择目标是 DOM 元素路径而非坐标点 |
| 主题（明暗） | 有。`prefers-color-scheme` + host `data-theme`/`.theme-*` 覆盖，MutationObserver 跟踪 | control.js:7-37, control.css:36-64 | 默认 dark（control.js:25） |
| 全屏原型页 vs 浮动层 | 原型 iframe 占满视口，control bar 浮在其上；drawer 展开时有自制 scrim | control.css:197-206 | scrim 非模态 dialog 的 ::backdrop 替代品 |
| 提交后 done 页 | 有。POST 后返回独立 done 卡片页，随后窗口自动关闭 | browser.py:364-396 | 非继续画布，是会话终结 |

## 3. 状态维度

| 能力 | 当前实现 | 来源文件:行号 | 备注 |
| --- | --- | --- | --- |
| 客户端状态（anchors/comments） | 内存数组 + 序列化进 hidden input `anchors_json`（`{selector,label,comment,tag}`） | control.js:52-56, 129-133, control.html:3 | **页面刷新即丢**，无 localStorage/无恢复 |
| 提交（表单 POST → server） | 有。`/decide` POST `choice/feedback/anchors_json/dpb_token/dpb_round`；`_parse_anchors` 限 40 条、label 120/comment 500/tag 40 截断 | browser.py:632-673, 338-360 | 一次性 token 注入 hidden 字段（browser.py:402-427） |
| 服务端持久化（决策权威） | 有。原子写 `decision-round-N.json`（binding + outcome），`os.replace` 同目录临时文件 | transaction.py:611, 254-269 | binding 含 round/prototype_html_hash/report_ref/summary/options + SHA-256 digest（transaction.py:276-290） |
| 投影（confirm + log） | 有。`confirm-round-N.json`（当 user_confirmed）+ `log.md` 确定性重建 | transaction.py:418-448, 374-406 | log 是决策 entry 的投影，不存储独立事件流 |
| 轮次（round-N） | 有。`round-{n}.html` 命名 + binding round；同 round 冲突 fail-closed"use next round" | transaction.py:36-48, 546-563, 28-33 | path 模式下 preview dir 取 path 父目录，html 模式写 `.scratch/preview-adapter/preview/`（transaction.py:28-33） |
| 轮次间共享 / 跨轮恢复 | 无客户端恢复。服务端有 same-binding retry 修复缺失投影（不开浏览器） | transaction.py:546-555 | retry 要求 binding digest 一致，否则 TransactionConflict |
| history（可回放的操作历史） | 无操作级 history。log.md 仅轮次级审计投影 | transaction.py:374-406 | 不构成 undo 数据 |
| 撤销 / 重做 | 无（见 §1）。 | — | — |
| 并发 / 锁 / 恢复 | 有。`decision-round-N.lock` O_EXCL + 30s heartbeat + 3× 心跳 stale 判定 + binding 匹配才可回收 stale lock | transaction.py:133-251, 190-217 | 单 transaction/round，多端并发 fail-closed |
| 会话终结（超时） | 有。`done.wait(timeout=1800)` 超时按 aborted 收尾 | browser.py:706-712 | 窗口被 owned 进程杀掉（browser.py:713-722） |

## 4. 版本 / 历史能力

| 能力 | 当前实现 | 来源文件:行号 | 备注 |
| --- | --- | --- | --- |
| 快照 | 部分。**哈希级**快照：prototype HTML 的 SHA-256（LF 归一化），绑定进 decision entry | util.py:17-29, transaction.py:290 | 只证明"原型没被改"，非内容快照/恢复点 |
| 轮次原型留存 | 有。每轮 `round-N.html` 文件（html 内联模式自动写出） | transaction.py:36-48 | fixture/showcase 可见多轮文件（g5-multi-round-last-confirmed/preview/round-1.html、round-2.html） |
| diff | 无。无任何 diff 能力（HTML 级或渲染级） | — | — |
| 命名版本 | 无。只有 round 序号；`report_ref` 指 decision report 而非版本 | transaction.py:280-290 | 版本 id 概念仅存在于 report_ref 字符串 |
| 分支 | 无。round 线性递增；不同 binding 的同 round 直接冲突并拒绝 | transaction.py:546-563 | "use next round" = 无回填/无分支 |
| 跨版本锚点一致性 | 无。anchor 是 cssPath，跨轮 HTML 变更后旧 selector 可能失效 | control.js:73-107 | 无元素身份（node id）绑定，只有路径 |

## 5. 协作能力

| 能力 | 当前实现 | 来源文件:行号 | 备注 |
| --- | --- | --- | --- |
| 单端 / 多端 | 单端。一次一个 preview 窗口；lock + first-decision-wins 保证单决策 | browser.py:43-88, transaction.py:190-251 | 无多端同步/共享 session |
| 冲突合并 UI | 无。冲突是 fail-closed 拒绝（返回错误信息），无合并/解决 UI | transaction.py:546-563, browser.py:648-673 | 双份 floor / binding 不一致都以错误返回 |
| 共享评论 / 多角色 | 无。只有当前评审者自己的 feedback/anchors | — | 人审单用户会话 |
| postMessage 协作通道 | 部分。仅 parent↔iframe 单向锚点数据（`dpbPinAnchor`） | browser.py:531, control.js:556-580 | 不是多端通道 |

## 6. 可访问性 / 移动端

| 能力 | 当前实现 | 来源文件:行号 | 备注 |
| --- | --- | --- | --- |
| 键盘操作（drawer） | 有。非模态 `dialog.show()`（非 showModal，避免页面 inert——pin 需点到原型）；ESC 关闭/退出 pin；pin off 时 Tab trap；关闭后焦点恢复 | control.js:313-335, 473-492 | 手写 trap 替代 showModal 的焦点陷阱 |
| 键盘快速提交 | 有。textarea 内 Ctrl/Cmd+Enter 提交 primary | control.js:394-402 | I8 |
| 键盘 pin 导航 | 部分。pin on 时 Tab 放行到原型（control.js:480）；但选中元素仍需 click（无纯键盘选择路径） | control.js:479-492 | pin 依赖 hover + click |
| 屏幕阅读器 | 有。`role=status`/`role=alert` + sr-only live regions：pill ready 状态、abort/pill-confirm arm 广播、`aria-live="polite"` anchors 列表、按钮 `aria-description` | control.html:11,19,41,57; control.js:245-259, 416-431 | P1.6 缓存 readiness 防 SR 抖动（control.js:264） |
| 焦点 / 语义标记 | 有。`aria-haspopup=dialog`、`aria-pressed`、`aria-invalid`、`aria-label`、tabular-nums | control.html:14,17,33,50-52 | P1.1 直接确认时移除 aria-haspopup（control.js:271,284） |
| reduced-motion | 有。`@media (prefers-reduced-motion: reduce)` 关 transition/animation（armed 态靠实色+粗体兜底） | control.css:473-482 | — |
| 移动端布局 | 有。`@media (max-width:720px)`：pill 右 12px、drawer 全宽、pill-info 隐藏、按钮堆叠；720 内 revise 按钮不隐藏（debate 决定） | control.css:463-472, 169-172 | 移动端可用性，非专用移动交互 |
| 本地化 | 有。zh-CN / en 双语言，env `DPB_PREVIEW_LANG`/`LANG` 选择，按钮 label 本地化但提交值保持原始 option | i18n.py:16-118, 122-128; control.py:40-55 | CJK-first；未知 locale 回落 zh-CN |

## 7. 外部契约

| 能力 | 当前实现 | 来源文件:行号 | 备注 |
| --- | --- | --- | --- |
| 上游工具 `preview_prototype` | schema：`path`/`html`（二选一）、`summary`、`round`、`report_ref`、`options`（可选，默认按 locale） | server.py:38-80 | 返回 `confirmed/floor_pass/selected_options/feedback/anchors/round/confirm_record_path/aborted/decision_id`（transaction.py:451-464） |
| stdio 传输 | JSON-RPC over stdio（Content-Length 或 newline），单工具分发；preview 对坏帧 fail-fast | _transport.py:119-146, server.py:123-129 | 与 evidence 共享 wire 格式（ADR-0009） |
| 下游 `/decide` | HTML 表单 POST；一次性 token + round 绑定 + first-decision-wins session | browser.py:43-88, 632-694 | token 缺失/复用/round 不匹配 → fail-closed（browser.py:648-666） |
| 下游持久化产物 | `decision-round-N.json`（决策权威）+ `confirm-round-N.json`（确认权威）+ `log.md` | transaction.py:611, 418-448 | ADR-0013：决策 entry 是审计/恢复权威，**不是**确认权威（ADR-0013:19） |
| G5 不变量 — feedback floor | 双实现：服务端 `_check_feedback_floor`（非空 feedback OR ≥1 anchor，且每个 anchor 有 selector+comment）+ 前端 `isSubstantive()` mirror | transaction.py:51-78, control.js:228-236, 636-659 | 结构性不判语义（ADR-0008:22,26）；前端 mirror 只做 UX，服务端权威（ADR-0008:24） |
| G5 不变量 — 原型完整性 | served `prototype_html_hash` 必须等于 binding hash，否则 TransactionConflict | transaction.py:586-592 | LF 归一化防 Windows autocrlf 噪音（util.py:17-29） |
| G5 不变量 — trust boundary | iframe sandbox 无 `allow-same-origin`，token 藏于 parent 表单，桥不触 parent DOM | browser.py:565-580, 430-451 | 由 test_browser_control.PinAnnotationBridgeTests 锁定（test_browser_control.py:600-639） |
| 编排器探测 | orchestrator 探 `tools/list` 找 `preview_prototype`；缺失则跳 preview 直接进 Fill | design-playbook-preview/README.md:10-11 | — |
| 兼容 launcher | `packages/design-playbook-preview/server.py` 是 runpy 转发到主插件 runtime | design-playbook-preview/server.py:14-29, README.md:5-8 | 不是首选路径 |

## 8. 已知 trade-off / 痛点（从注释标签 + ADR 抽取）

| 标签 | 痛点 / 决策 | 来源文件:行号 |
| --- | --- | --- |
| I1 | floor 拦截提交时不强制开 pin 模式——曾尝试强制，是"意图猜测"，用户可能只想要整体意见 | control.js:657-658 |
| I2 | "批注"与"评审确认"两个 pill 按钮曾都只是开 drawer，现分离 intent（批注=直接进选择，确认=评审） | control.js:337-343 |
| I4 | ADR-0008 结构化 floor 只判"非空"，无最短长度；语义垃圾（如"安师大"）放行，归 G6 ui-evaluator | control.js:228-236, control.css:330-333; ADR-0008:22,26 |
| I8 | Ctrl/Cmd+Enter 在 feedback 内提交 primary——两条提交路径必须共享 submitPrimary 防分叉 | control.js:345-349, 394-402 |
| I13 | pill primary 在 ready→not-ready 翻转时要恢复原 label；一度直接确认 label 残留 | control.js:238, 269, 285-288 |
| I18 | 终止/确认都要二次点击 arm（防误杀评审会话），arm 4s 超时；ESCAPE/重开 drawer/其他点击都需清理 armed 态 | control.js:404-410, 330-331, 447-451, 461 |
| P1.1 | pill 直接确认时移除 `aria-haspopup`（不再是 dialog 触发器），not-ready 时恢复 | control.js:271, 284 |
| P1.5 | 自制 scrim 在 pin-off 时拦截点击关闭 drawer，pin-on 时 `pointer-events:none` 放行点击到原型 | control.css:197-205, control.js:382-387 |
| P1.6 | readiness 变化缓存，避免每次输入都触发 SR 播报抖动 | control.js:264 |
| — | G5 sandbox（无 allow-same-origin）破坏同源 pin → 需要桥 + **双份 cssPath 复制**（browser.py 与 control.js 各一份），需防漂移 | browser.py:449-451, control.js:73-107, browser.py:467-501 |
| — | 跨源 anchor `el=null`：parent 无法读 iframe innerText/aria-label，label 只能由 tag+selector 叶子推导 | control.js:119-127 |
| — | MEDIUM-1：伪造 POST 不得终止 session（否则一个 iframe fetch 就能 DoS 掉 G5 门）；done.set() 只在带 token 的 POST 后触发 | browser.py:683-694 |
| — | 客户端状态零持久化：刷新丢所有 anchors/comments（hidden input 只是表单载体） | control.js:129-133 |
| — | 锚点用 cssPath 表达：原型变更即失效，无元素身份绑定 | control.js:73-107 |
| — | floor 双实现（JS mirror + Python authoritative）靠 `--self-check` 与 playwright 测试锁步 | ADR-0008:24, 51-58 |
| — | ADR-0013：决策 entry 是审计权威不是确认权威；投影（confirm/log）可能缺失需同 binding retry 修复 | ADR-0013:19-23 |
| — | lock 超时 / stale 回收需 binding 匹配，否则报"use next round"（跨端抢占失败是硬错误） | transaction.py:145-187, 546-563 |
| — | 单轮单决策：无版本化、无分支、无 diff——与目标"Figma/Stitch 级别 + 本地版本控制"差距最大的维度 | ADR-0013:23-24（lock 语义） |

---

## 9. 摘要

- 矩阵共 **8 个维度、约 46 个能力项**。当前 surface 是**批注覆盖层而非可视化编辑器**：交互仅 pin 选择 + 批注文本；渲染是"受信任 parent 页 + sandboxed iframe"双 DOM 结构（跨源靠 postMessage 桥）；状态是"内存 + 表单 POST + 原子 JSON 持久化"；版本能力仅有哈希与轮次文件，无 diff/分支/命名版本；协作是严格单端 fail-closed。
- 已知痛点高度集中在 G5 信任边界引发的连锁成本（桥/双份 cssPath/el=null label 退化/二次点击 arm 状态机）与 floor 结构性局限。
