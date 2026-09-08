design-baseline: not-applicable:new standalone UI; router requires_baseline=false
scene: read-only source-document reader
density: reading-focused; 18px body; no metrics dashboard
template: detail page with a persistent journey/source navigation region
regions: navigation -> spec L2 directory duty; main -> current source and its boundary; status -> current case/source identity; action -> search clear and error recovery only
components: document navigation -> new native anchors (no existing host component library); search -> new native input type=search (offline title/source filtering); source text -> new pre with textContent (untrusted markup must not execute); provenance -> new text definition list (not a status approval badge)
baseline-changes: none
risks: historical approvals belong to their own task; command text is read-only documentation; no backend job execution; disabled JavaScript has a visible limitation rather than fake success

# 案例阅读器 — 设计方向

## 明确的人审输入

- 范围及 P2 全审计来自 shaping/confirm-round-1.json，decision_id: da9272548f03496bbcc170024b036c9a。
- 字体放大至 18px，行高 1.75；正文源文本 16px，支持换行。
- 页面底色浅绿，正文偏白；墨绿色只用于选择态、交互和标题层次，不做通过 / 失败的暗示。
- 本轮展示外观和阅读结构，不能替代原文一致性、键盘、窄屏和离线运行检查。

## Tokens

```text
--page: #e8f2e7
--surface: #fbfdf9
--ink: #183326
--muted: #4b6557
--accent: #23583e
--line: #bdd0bd
--selected: #d3e6cf
--font-cn: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif
--body-size: 18px
--source-size: 16px
--line-height: 1.75
--space: 8px
--radius: 8px
--focus: 3px solid var(--accent)
```

## DD-0001 — 如何保持案例来源与旅程可见

```yaml
id: DD-0001
tier: compare
question: 在已确认的目录加原文布局内如何承载材料切换
status: confirmed-agent
constraints:
  baseline: waived:no pre-existing product baseline; router requires_baseline=false (new standalone reader, plan.md skipped list)
  spec: [l2.layout, l6.c1, l6.c3, l6.c4]
  rules: [DECIDE-01@1]
candidates:
  - {id: A, source: agent, created_at: 2026-09-08T10:11:31+08:00, fidelity: description, summary: 原生目录链接切换主正文并保留 URL, deviations: none, assets: []}
  - {id: B, source: agent, created_at: 2026-09-08T10:11:31+08:00, fidelity: description, summary: 同页所有材料用折叠区域承载, deviations: none, assets: []}
comparison:
  axes:
    - {axis: 来源上下文 spec L6.1, A: 同时展示目录归属与当前材料边界, B: 多份展开会让不同案例连续混读}
    - {axis: 锚点恢复 spec L6.3, A: URL 直接标识唯一材料, B: 需要额外协调多个折叠状态}
  tradeoffs: A 只显示一份原文便于归属核验；B 可连续阅读但长文堆叠让来源界限弱化
selection:
  candidate: A
  rationale: 本次内容包含三份不同来源的历史任务与命令说明；唯一当前原文配明确来源可避免混用确认或 Pass，不是任意文档页都需要的证据边界提示
  rejected:
    - {candidate: B, reason: 历史材料容易合并阅读且恢复语义不如唯一材料明确}
confirmation:
  kind: agent
  via: agent-record
  confirmed_at: 2026-09-08T10:11:31+08:00
supersedes: null
```

## 原型到实现的边界

Preview 只表现布局、字体、色彩和阅读语义；Fill 重新实现真实目录与原文绑定，不复制原型源文件。保留浅绿色但不沿用原型中用于示意的材料摘录作为验收证据。
