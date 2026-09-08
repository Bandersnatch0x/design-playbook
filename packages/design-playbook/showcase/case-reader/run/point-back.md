# Point-back — case-reader Fill (current end-to-end run)

## Evidence ledger

```text
criterion: L6.1
required:  真实源文件对照自动检查；默认 / 所选材料截图与 a11y tree；所有材料逐项核验
observed:  evidence/L6.1-a11y-tree.json 首篇材料全文字段在 a11y tree 中逐字核验；selfcheck.py 对 4 份内嵌文档做字节一致 + SHA-256 断言通过；Playwright 断言 4 份文档 textContent === 源文件解码文本、来源路径与 SHA-256 显示正确（a-spec/a-decision/a-review/b-confirm 全 True）；命令说明材料以摘录引用命令文档（run-status.md / run-handoff.md 存在性检查通过）
result:    pass
```

```text
criterion: L6.2
required:  搜索交互自动检查；无结果截图；清除后结果恢复断言
observed:  evidence/L6.2-empty-search-v2.png
note:      交互轨迹 evidence/L6.2-search-clear.json；断言：过滤「需求」时 a-spec 可见、a-review 隐藏，正文不受过滤替换；「zzz」进入 empty 态并显示清除入口；点击清除后全部 6 项恢复且输入框清空
result:    pass
```

```text
criterion: L6.3
required:  深链接 / 刷新 / 历史自动检查；错误状态截图和恢复交互
observed:  evidence/L6.3-unknown-fragment-v2.png
note:      交互轨迹 evidence/L6.3-deeplink-history.json（深链 #a-review、点击切换、后退/前进）；断言：无效片段显示错误视图且正文隐藏、恢复链接返回首篇、后退/前进恢复所选文档
result:    pass
```

```text
criterion: L6.4
required:  三视口截图与几何断言；Tab / Enter 和焦点检查；无脚本状态截图或 a11y tree
observed:  evidence/L6.4-desktop-1440.png
note:      另有 evidence/L6.4-tablet-768.png 与 evidence/L6.4-mobile-390.png；scrollWidth ≤ 视口宽度断言 390/768/1440 全通过；evidence/L6.4-keyboard.json 键盘轨迹（Tab×2 + Enter 后焦点落在正文标题）；noscript 提示在源码中静态存在（禁用脚本时显示能力限制说明）
result:    pass
```

```text
criterion: L6.5
required:  断网、原文 textContent 与无脚本注入检查；真实交付副本复跑
observed:  断言：Playwright 监听整个会话零非 file:// 请求（no-external-reqs=True）；原文以 textContent 写入 pre，HTML 标记不可执行（selfcheck.py 源码检查 + a11y tree 原样文本）；交付副本 run/evidence/static-handoff/deliverable.html 复跑同一断言集全绿
result:    pass
```

## Findings

```text
issue:    初版 showError 使用 style.display='' 回退到 CSS 类 display:none，无效片段时错误视图不可见
source:   spec
fix:      style.display='block' 显式覆盖；同时 initial hash 无效时不再静默回退首篇而是进入错误视图
severity: S3
track:    product
confidence: high
disposition: blocking
evidence: evidence/L6.3-unknown-fragment-v2.png
```

- closes: 初版 showError 使用 style.display='' 回退到 CSS 类 display:none，无效片段时错误视图不可见 -> recirculate -> fix (index.html error-view display='block') -> re-eval (L6.3 断言重跑全绿 + 重新捕获错误态截图) -> 0 blocking

```text
issue:    L6.5 声明的「真实交付副本复跑」在本次 point-back 初版时点尚未执行（run-handoff 未运行）
source:   spec
fix:      执行 run_handoff.py 生成交付包并在 deliverable.html 上复跑同一断言集
severity: S1
track:    product
confidence: high
disposition: advisory
evidence: run/plan.md 执行与接续
```

交付副本复跑已补齐（advisory 修复后状态）：run_handoff.py 构建交付包；deliverable.html 上 13 项断言全绿。另记录一次交付构建修复：初版 Fill 通过外链 `_gen_docs.js` 引用文档集，run-handoff 复制 Fill 单文件时交付副本不可用（nav 为空）。修复为把 DOCS 字面量内联进 index.html（单文件自包含，符合 spec L2「内嵌」），selfcheck 增加「禁止外链 + 内联与生成器一致」检查，重建交付包后复跑通过。

## Positive findings

```text
issue:    原文一致性由三层独立证据承载：字节级 selfcheck、a11y tree 逐字核验、Playwright textContent 断言
source:   spec
fix:      -
severity: S0
track:    cross-cutting
evidence: showcase/case-reader/selfcheck.py; evidence/L6.1-a11y-tree.json
```

```text
issue:    错误态 / 空态通过 body[data-state] 暴露，Provider observed_state 如实返回 error/empty 而非 unknown
source:   craft
fix:      -
severity: S0
track:    cross-cutting
evidence: evidence/manifest.jsonl
```

## Coverage statement

必审（exhaustive）完成状态：complete — P1（目录→选择→阅读→旅程切换，4 份文档 + 2 份命令说明全部逐项核验）、P2（搜索命中/无匹配/清除）、P3（深链/无效片段/恢复/后退/前进）、P4（三视口几何 + 键盘路径）全部完成，覆盖 spec 全部五项 L6 与五态矩阵（initial/success/failure/empty；loading 为 n/a 同步内嵌数据）。
Explicit unreviewed: prefers-reduced-motion 与打印样式未做交互级复验（表面无动画，静态检查通过）；物理断网复测未做（以零外部请求 + 源码无网络 API 承载）。

## Limitations statement

- 本评审为当前 agent 的声明驱动评审（plan.md 既定边界），不声称独立专家评审、设备实验室或外部用户试用。
- 本次运行为 text-face 主导评审：断言基于 HTML/CSS 源码、a11y tree 文本与 Playwright DOM 断言；截图作为路径绑定证据保留，未做视觉判读。
- 交互轨迹文件为 Playwright trace zip 格式，其内部帧未逐帧人工回放；结论依据同页 DOM 断言。
- 断网断言以「零非 file:// 请求 + 源码无网络 API」承载，未做物理断网复测。
- Pending user adjudication: 无（无 judgment-class S3）。

## Verdict

Pass
