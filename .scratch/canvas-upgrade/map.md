# Wayfinder map — canvas upgrade（画布能力升级到 Figma/Stitch 级别 + 本地版本控制）

Label: wayfinder:map

## Destination

**已锁定（2026-08-07，[04 grilling](issues/04-lock-destination.md)）**：把 preview canvas（G5 人工确认门的 floating 批注覆盖层）升级为"**厚化 G5 反馈循环到准画布评审**"——**不追 Figma/Stitch 级别**（该级别需 10/11 项必须能力，是新产品量级，改变产品性质）。

本 effort 能力面（方向 A 可达的最大增量）：
- **版本控制**：事件溯源 + 命名快照叠加（round 级）——decision 链 = 事件（replay `state_at(N)` + fork 对比方案），`round-N.html` = 命名快照（命名 / 时间线浏览 / 非破坏性还原）
- **锚点 AST 化**：cssPath → node id（S3 局部）
- **交互改进**：多选 / 框选 / undo / draft 持久化

落地形态：`feature/canvas-thickening` 分支，下个 minor（v0.11.x），发布走 release transaction（受 ADR-0015 约束）。

**验收标准（2026-08-07 用户设定：执行到实现，不只规划）**：
1. **所有票 resolved**（06 原型 → 05a/05b 实现 → 07 交互改进 → 08 e2e）
2. **e2e 测试通过**：Playwright 驱动真实浏览器跑通完整流——preview 画布 → pin 锚点 → 反馈 → 确认 → 命名版本 → 时间线回看 → fork 派生，全部断言绿

## Notes

- **域**：`design-playbook` 插件（Claude Code / Codex），Design I/O 流水线 + 验收，不是独立产品。
- **当前 main = v0.10.0**，ADR-0015 stable-main 冻结 + 分发暂停。任何新能力需经 `feature/...` 分支 + release transaction，不入 main 直推。
- **画布所在**：`packages/design-playbook/mcp/preview/`，是 G5 人工确认门（`preview_prototype` MCP adapter）的 HTML 控制层，是反馈/锚点表面，不是设计表面。
- **域纪律**：参考 `docs/agents/issue-tracker.md`（markdown tracker）+ `CONTEXT.md` glossary；SSOT 在 `packages/design-playbook/skills/*/references/*`。
- **审计约束**：audit 全程只读，不动产品代码；产出为 markdown 资产（capability matrix、gap 表、interpretations 表），落入 `.scratch/canvas-upgrade/assets/`。
- **域文档消费**：写新能力文档前，先读 `CONTEXT.md` glossary 防术语漂移（"Declaration"、"Contract"、"Evidence"、"preview*"、"observe*" 等术语在本 effort 必须保持语义一致）。
- **执行 override（2026-08-07 用户指令："设置 goal 完成所有票并通过 e2e 测试"）**：本 effort 从 wayfinder 默认的"规划到目的地"改为**执行到实现**——resolve 剩余所有票（06/05a/05b/07/08）+ e2e 测试通过作为 Destination 验收。实现落 `feature/canvas-thickening` 分支（不碰 main，ADR-0015）。

## Decisions so far

<!-- One linked gist per resolved ticket. The full answer lives in that ticket. -->

- [01 — 当前画布能力矩阵](issues/01-current-canvas-matrix.md) — 8 维度 46 项；现有 surface 是 G5 floating 批注覆盖层（pin+comment），非可视化编辑器；渲染=受信任 parent + sandboxed iframe 双 DOM；版本能力仅哈希+轮次文件，无 diff/分支/命名版本；协作严格单端 fail-closed。资产 `assets/current-canvas-matrix.md`。resolved 2026-08-07
- [02 — Figma/Stitch 目标能力基线](issues/02-figma-stitch-target-baseline.md) — 三层 18 项（核心 6 / 结构 5 / 扩展 7），**必须 11 项**；Stitch=Google Stitch（AI 生成优先，无公开图层/版本），基线以 Figma 词典为主干，与 SSOT components/design/template 对齐。资产 `assets/figma-stitch-target-baseline.md`。resolved 2026-08-07
- [03 — 本地版本控制解释空间](issues/03-local-vc-interpretations.md) — 6 形态对比；当前 round 机制已是"事件日志+快照+投影"雏形；**高契合=事件溯源(补 replay/fork)+快照列表式+命名版本**；低契合=git/pijul/CRDT（单用户无 merge 场景）；不锁定选型。资产 `assets/local-vc-interpretations.md`。resolved 2026-08-07
- [04 — 锁定目的地](issues/04-lock-destination.md) — **D1=纯 A**（厚化批注画布，minor）；**D2=目的地重定义**为"厚化 G5 反馈循环"，不追 Figma/Stitch 级别；**D3=事件溯源 + 命名快照叠加（round 级）**；D4/D5 作废。resolved 2026-08-07
- [05 — 版本控制数据模型](issues/05-vc-data-model.md) — 事件溯源不建新存储（entry 即事件，补 `state_at`/`fork`）；命名快照=新权威 `version-<seq>.json`（元事件）；锚点局部 AST 化（anchor v2 可选 `node_id`+`features`）；纯新增不破坏读侧，G5 零冲突。资产 `assets/vc-data-model.md`。resolved 2026-08-07

## Not yet specified

<!-- Fog toward the destination; graduates as frontier advances -->

- **UX 原型**（06 prototype 票）：命名版本 + 时间线浏览 + replay/fork 的交互形态，需 rough artifact 给用户反应——现 unblocked。
- **交互改进细节**：多选 / 框选 / undo / draft 持久化的具体行为——随 06 原型 + 实现票定。
- **版本控制实现拆解**（05a/05b 实现票）：`versions.py`（state_at / fork / create_named_version / timeline）+ anchor v2 提交侧生成——schema 已定（05 资产），实现范围待 06 原型 UX 确认后落。
- **渲染层 / 协作模型 / 设计令牌 / 自动布局**：方向 A 排除（DOM 现状保持、单端、无令牌/布局引擎）——已从本 effort 雾中移除。
- **发布时序**（外部依赖，不阻塞 A 开发）：release transaction 受 ADR-0015 约束；分发恢复（3b community catalog）由外部账号驱动。

> 05 已 resolve（2026-08-07）：数据模型设计完成（`assets/vc-data-model.md`）——事件溯源不建新存储、命名快照=`version-<seq>.json` 元事件、锚点局部 AST 化、纯新增零冲突。06 原型现 unblocked。

## Out of scope

- 不在 stable-main 冻结解除前向 `main` 推任何新能力（ADR-0015）。
- 不在 audit 阶段改产品代码（read-only 约束）。
- 不与活跃分发恢复线（3b community catalog）耦合——它是外部账号驱动，本地图独立。
- 不与当前 active feature cycle 抢资源（CONTEXT.md 明确"no active feature cycle"；新 effort 入 `feature/...` 分支，不在 `main`）。
- 不把"本地版本控制"等同于 git 二进制集成（产品语义优先，git 只是可能底层之一）。
- 不讨论 v0.10 之前的回填 capability——本 effort 落在 `feature/canvas-upgrade` 之上。

## Tickets

Tickets live under `issues/`.

- [01 — 当前画布能力矩阵](issues/01-current-canvas-matrix.md) — resolved 2026-08-07。资产 `assets/current-canvas-matrix.md`。
- [02 — Figma/Stitch 目标能力基线](issues/02-figma-stitch-target-baseline.md) — resolved 2026-08-07。资产 `assets/figma-stitch-target-baseline.md`。
- [03 — 本地版本控制解释空间](issues/03-local-vc-interpretations.md) — resolved 2026-08-07。资产 `assets/local-vc-interpretations.md`。
- [04 — 锁定目的地](issues/04-lock-destination.md) — resolved 2026-08-07。D1=纯 A / D2=重定义 / D3=事件溯源+命名快照叠加。
- [05 — 版本控制数据模型](issues/05-vc-data-model.md) — resolved 2026-08-07。资产 `assets/vc-data-model.md`。
- [06 — 命名版本 + 回放 UX 原型](issues/06-prototype-named-versions-ux.md) — resolved 2026-08-07。资产 `assets/prototype-named-versions-ux.html`。
- [05a — versions.py 实现](issues/05a-versions-py-implementation.md) — resolved 2026-08-07。`mcp/preview/versions.py` + test_versions.py 10 测试。
- [05b — anchor v2 实现](issues/05b-anchor-v2.md) — resolved 2026-08-07。`browser._parse_anchors` v2 + test_anchor_v2.py 5 测试。
- [07 — 交互改进](issues/07-interaction-improvements.md) — resolved 2026-08-07。draft 持久化（DPB_DRAFT_KEY + localStorage）+ undo（Ctrl/Cmd+Z）。
- [08 — e2e 测试](issues/08-e2e-tests.md) — resolved 2026-08-07。`tests/test_e2e_canvas_vc.py` 3 测试全绿（Playwright 真浏览器全流）。

## Frontier

**✅ 全部 10 票 resolved（2026-08-07）。Destination 达成（验收 1/2：所有票完成；验收 2：e2e 通过）。**

实现落点：`feature/canvas-thickening` 分支的候选变更（versions.py / anchor v2 / draft+undo / e2e），发布工程（release transaction，ADR-0015）不在本 map 执行范围。

**注意（2026-08-07）**：仓库 git 对象库损坏（HEAD tree / stash / 大量 refs missing，预先存在）；本次已从会话上下文完整重建全部改动文件，但 git 仓库本身待用户决策（建议从 origin 重新 clone 或修复 reflog）。