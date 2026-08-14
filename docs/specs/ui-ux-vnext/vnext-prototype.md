# vNext 产品表面、兼容边界与首个验证切片（Product surface, compatibility boundary & first validation slice — decision model prototype）

- 工单：#33（wayfinder:grilling，收官票）。域：跨域收官——把 #24-#32 六份定稿原型落为「可直接实施的 vNext 规格」：产品表面映射、工件与校验器变更、兼容边界、可选面边界、首个 Web 验证切片、版本化交付切片与实现工单图（地图最后一条 Not yet specified 的答案）。
- 状态：**已定稿**。2026-08-14 用户裁决：8 项待决问题全部按建议采纳（Q1-Q8，见第 8 节「已确认决议」）；正文按决议收敛。本文即「可直接实施的 vNext 规格」定稿。
- 性质：纸面决策模型（规划型地图产物）。不实现产品代码、不改技能与脚本；实现工单按决议 Q2=B 执行——仅创建 S1 一张实现 issue，S2-S6 待 S1 落地验证后再建。
- 上游锁定决议（不可推翻，只落地）：#24 矩阵（8 域 + 全局原则 + Q1-Q8）；#28 成形（S0-S6、CP-A~E、会话工件、契约 v1 零破坏）；#29 评审（双轨+横切、六块报告、severity 分轴+兼容别名、方法语义 manifest 可选键、R1-R5）；#30 规则治理（rules.md 注册表、G8、craft-guard 迁移与七列行、rules-governance.jsonl、三条占位规则）；#31 设计决策（R/C/E 三档、DD 条目块、provider 数据契约、资产引用层）；#32 闭环（LR0-LR10、P1/P2/P3 三档、G9-G12、run-profile 块、19 项工件清单、12 类重入、verdict 两值不扩）。

---

## 0. 输入基线：已发布面的真实清单（表面映射的对照面）

已发布版本：**v0.14.1**（2026-08-14，npm 锁步发布组 `design-playbook` + `dsh-design-playbook` 同版本，stable main 政策 = main 与最新正式发布一致）。vNext 一切变更以此为兼容基线。

| 面 | 已发布清单（逐项点名） |
| --- | --- |
| 技能（8） | `design-playbook`（编排）、`design-baseline`、`reference-intake`、`ux-spec`、`ui-picker`、`craft-guard`、`native-craft`、`ui-evaluator` |
| 命令（6） | `/design-io`、`/ux-spec`、`/ui-review`、`/run-review`、`/run-status`、`/doctor`（均在 `packages/design-playbook/commands/`） |
| run 级门禁 | G1（`g1_spec.py`）、G2-G4（`g2_g4_pointback.py`）、G5（`g5_preview.py`）、G6（`g6_evidence.py` + `g6_records.py` + `g6_warnings.py`）、G7（`g7_contract_drift.py`），由 `validate_run.py` 编排 |
| 产品级校验 | `scripts/validate.py`（JSON 清单、技能/命令结构、**craft 检测器协议段**——detectors.md 六字段块 + 四份 fixture 行形状、技能 prose 锚点）；`scripts/doctor.py`（安装面健康）；`scripts/aggregate_runs.py`（跨 run 重复阻塞统计，JSON 契约面） |
| 契约机械层 | `scripts/contract_v1.py`（contract.json / decisions.jsonl / bind_first / contract-bind.json）；`scripts/stages.py`（stage registry，十段 + 固定工件名）；`scripts/run_status.py`、`verdict_syntax.py` |
| MCP 运行时 | `mcp/preview/`（transaction / versions / integrity，G5 消费）；`mcp/evidence/`（server / capture_contract / ledger_syntax，G6 消费） |
| 示例（fixture） | `examples/craft-detectors/` 四份（saas-dashboard / composition-contrast / landing-product-contrast / existing-brand-contrast）、`ops-list-spec.md`、`point-back-findings.md`、`settings-decision-report.md`、`reference-intake/` |
| CI 面 | `.github/workflows/ci.yml`：`scripts/validate.py` → `scripts/doctor.py` → `packages/design-playbook/tests/test_validate_run.py` → 根 tests 单测群 → MCP stdio 门禁（preview/evidence，纯路径必跑 + chromium 捕捉组）→ 前端 floor |
| 文档面 | `README.md` / `README-zh.md`（技能命令表、适配器表）、`docs/agents/product-workflow.md`（命令表 + 可选适配器两节）、`docs/agents/release-checklist.md`、`docs/adr/`、`docs/releases/` |

---

## 1. 产品表面映射（逐技能逐命令处置表）

处置动词沿用矩阵第 2 节：**深化**（既有技能/命令加深）、**拆分/合并**（内容迁出、原位降级）、**保留不动**、**保持可选**。每行注明 vNext 表面变化（新命令/新参数/新工件/文档变化）。

### 1.1 技能面（8 个全部点名）

| 技能 | 处置 | 归属域 | vNext 表面变化 |
| --- | --- | --- | --- |
| `design-playbook`（编排） | **深化** | 跨域（LR0-LR10） | SKILL.md 增档位定档节（LR1：P1/P2/P3 初判 + 用户一次确认 + 升档自动/降档用户）与 run-profile 写入义务；`references/load-map.md` 增 shaping/rules 工件装载说明；两轮停止语义保持（机器计数归切片 4）。**无新命令、无新参数** |
| `ux-spec` | **深化** | D1 成形 + D2 建模 | SKILL.md step 1 由「即兴提问风格」升级为 S0-S6 会话状态机（CP-A/B/C/E 批次、问题疲劳上限、投影函数序）；step 0 bind-first 前置为 S0 装配；**新工件** `.scratch/<run>/shaping/shaping-log.jsonl` + `queue.json`；`references/spec-template.md` 增 L2-L5 结构化字段（逐页职责表、路径表、逐页五态矩阵）；G1 深化（见 2.2） |
| `ui-picker` | **深化** | D3 设计决策 | SKILL.md step 4 落 R/C/E 三档触发与 DD 条目块写法（顶块逐字保留）；现行「2-3 IA 变体分支」正式化为 C 档；**新工件面** `.scratch/<run>/candidates/`（provider 资产引用层，path+sha256）；provider 匿名数据契约（候选描述符）写入 `references/` 或 SKILL 正文；G10 校验（见 2.2） |
| `craft-guard` | **拆分/合并**（原位降级为引用层） | D7 注册表 + D4 执行 | `references/detectors.md` 八条六字段块整体迁入 `skills/design-playbook/references/rules.md`，detectors.md 改薄引用层（指向注册表 + 七列行格式 + 执行说明）；SKILL.md 行格式改七列（Applicability 拆列、N/A 并入三态）；hierarchy/loading tiers/motion 三段工艺清单**保留在技能内**（craft 声明本体）；`references/craft.md` 不动 |
| `ui-evaluator` | **深化** | D4 评审 + D5 证据 + D6 回流 | SKILL.md：三轨维度清单（产品/交互/横切）、finding 附加字段行（track / severity S3-S0 / confidence / disposition / evidence / assumes / rule: / dd:）、六块报告结构、R1-R5 两跳路由、blocking 处置权不变；`references/repair.md` 增第二跳映射表 + `invalidated:` 失效证据集块 schema；`references/a11y-tree.md`（ADR-0016 附接规则）与 `references/rubric.md` 原样保留；G2-G4/G6 消费面零改动 |
| `design-baseline` | **保留不动**（微扩一条记录面） | D3（输入侧权威） | 唯一变化：#31 6.2 基线漂移复核三出口（保持/修订/升级呈报）的 stale 复核记录行并入既有「发现/确认/重验」记录面（state.json 语义不变）。prepare/confirm/verify、防伪造、来源哈希全部原样 |
| `reference-intake` | **保留不动** | D3 输入侧 | 零改动（observed/inferred + Keep/Change/Do not copy 契约原样） |
| `native-craft` | **保留不动**（非 Web 面） | 声明层 | 零改动；非 Web 自动验证适配器维持出范围（地图 Out of scope），vNext 不为其新增执行面 |

### 1.2 命令面（6 个全部点名）

| 命令 | 处置 | vNext 表面变化 |
| --- | --- | --- |
| `/design-io` | **深化**（描述更新，签名不变） | frontmatter 描述补「档位定档（P1/P2/P3）与回流循环」；正文不变（编排细节本就归技能） |
| `/ux-spec` | **深化**（描述更新，签名不变） | 描述补「成形会话（问题批次/假设批次/确认批次）与会话工件」；仍在 spec.md 停止 |
| `/ui-review` | **深化**（描述更新，签名不变） | 描述补「双轨评审 + 六块报告（point-back.md）」；输出说明由 issue/source/fix/severity 扩为四字段 + 附加字段行 |
| `/run-review` | **深化**（additive） | 报告头 `run-review/v1` **保留**；增「规则候选队列（派生视图，协议）」节——从 repeat blockers + finding 附加字段派生候选条目（distinct runs ≥3 且语境 ≥2 且 0 未解释误报），只呈报不写回；`aggregate_runs.py` JSON 契约面 additive（新可选键），既有键零改动 |
| `/run-status` | **深化**（读模型扩展） | `run_status.py` 恢复叙述识别新工件：run-profile 块（档位/跳过清单/升档事件）、shaping 会话（suspended/resumed 重放）、point-back 六块与 invalidated（重入计数）；输出格式向后兼容（新增叙述行） |
| `/doctor` | **保留不动** | 零改动（安装面健康诊断，不消费 run 语义；rules.md 属包内工件由 validate.py 校验） |

**命令入口结论（决议 Q6=A）**：vNext **不新增命令、不新增参数**——全部新能力经既有技能深化与工件扩展进入；成形会话经 `/design-io` 与 `/ux-spec` 深化承载（会话是 ux-spec 技能的有状态化改造，#28 5.3 既定）；日后若高频「单开会话」需求出现再增（additive 无破坏）。

### 1.3 文档与示例面

| 面 | 变化 |
| --- | --- |
| `README.md` / `README-zh.md` | 技能表补一行职责措辞更新（ux-spec 会话、craft-guard 注册表、ui-evaluator 双轨）；「Stack with ecosystem」表不动；新增「Run profiles（P1/P2/P3）」一小节 |
| `docs/agents/product-workflow.md` | 命令表不变；pipeline 图补 shaping/rules 工件位；「Optional adapters」两节增「缺席 = 显式 blocked 记录」一句 |
| `docs/adr/` | vNext 落码时按切片补 ADR（注册表载体、七列行格式、severity 别名换算、首切片 fixture 策略）——具体 ADR 编号由实现工单承担 |
| `examples/` | 四份 craft fixture 迁移七列；新增首切片 fixture run（见第 5 节） |
| `CONTEXT.md` / `map.md` | 本轮不动（约束既定）；术语行已在前序工单更新 |

---

## 2. 工件与校验器变更清单

### 2.1 工件：19 项清单落为文件路径级变更表

沿用 loop-prototype 第 3 节清单，落为具体路径与变更类型（新增 / 扩展 / 沿用）：

| # | 工件（路径） | 变更类型 | 具体变更 |
| --- | --- | --- | --- |
| 1 | `<project>/contract.json` | **沿用** | 零 schema 改动（#28 5.1 零破坏结论）；`contract_v1.py` 不动 |
| 2 | `<project>/decisions.jsonl` | **沿用** | 零改动（append-only、supersedes 原样） |
| 3 | `packages/design-playbook/skills/design-playbook/references/rules.md` | **新增**（产品级） | 20 字段条目块注册表：craft 八条（first-party/advisory）+ A11Y-01/RESP-01（first-party/advisory）+ I18N-01/PERF-01/SEC-01（placeholder/advisory）；头部含拆分条件（>30 条或 >3 家族）与 schemaVersion；G8 产品级校验 |
| 4 | `<project>/rules-governance.jsonl` | **新增**（项目级） | append-only 治理日志（事件 schema 首版只定义；只记用户决定性事件） |
| 5 | `<project>/DESIGN.md` + `.scratch/<run>/design-baseline/state.json` | **沿用**（微扩） | design-baseline v1 语义不变；stale 复核记录行并入既有记录面 |
| 6 | `.scratch/<run>/spec.md` | **扩展** | L2-L5 结构化字段（逐页职责表 / 路径表 / 逐页五态矩阵）；L1/L6 既有结构不动 |
| 7 | `.scratch/<run>/plan.md` | **扩展** | 头部 run-profile 结构化字段块（tier / 判据核对 / confirmed_by / 跳过清单 / 升档事件）——**档位块必写**，其余 plan 内容仍可选 |
| 8 | `.scratch/<run>/shaping/shaping-log.jsonl` | **新增**（run 级） | append-only 会话事件日志（12 类事件枚举） |
| 9 | `.scratch/<run>/shaping/queue.json` | **新增**（run 级，派生态） | 待答队列 / 假设批次 / 确认批次（可从 log 重建） |
| 10 | `.scratch/<run>/decision-report.md` | **扩展** | 顶块逐字保留；其后追加 DD 条目块（id/tier/question/status/constraints/candidates/comparison/selection/confirmation/supersedes） |
| 11 | `.scratch/<run>/preview/decision-round-<n>.json`、`confirm-round-<n>.json` | **沿用** | 零改动（E 档确认搭乘既有事务，options/selected_options 语义复用） |
| 12 | `.scratch/<run>/candidates/` | **新增**（run 级，可弃引用层） | provider 候选资产 path+sha256 引用；不入 manifest、不作证据 |
| 13 | `.scratch/<run>/filled-ui.html/.md` | **沿用** | 零改动 |
| 14 | `.scratch/<run>/craft-guard.md` | **扩展**（行格式破坏性重定义） | 审计行改七列：`| ID@ver | Applicability | Predicate reason / missing proof | Result | Rendered evidence | Source evidence | Exception check | Positive fix |`（Status 拆为 Applicability+Result，N/A 并入三态） |
| 15 | `.scratch/<run>/evidence/manifest.jsonl` | **扩展**（append-only 可选键） | 方法语义五键（method / observation / interpretation / scope / population+ethics）——旧读取方忽略未知键 |
| 16 | `.scratch/<run>/point-back.md` | **扩展** | 三段 → 六块（+Positive findings / Coverage statement / Limitations statement）；`invalidated:` 失效证据集块；finding 附加字段行；**机器面四字段一字不改** |
| 17 | `.scratch/<run>/contract-bind.json` | **沿用** | 零改动（bind_first 快照原样；assumed 老化计数从这里派生） |
| 18 | `.scratch/<run>/reference/contract.md` + `manifest.json` | **沿用** | 零改动 |
| 19 | stage registry（`packages/design-playbook/scripts/stages.py`） | **沿用** | **零改动**（shaping/candidates 非 stage 标记；spec stage 仍指向 spec.md；`craft-guard.md` 工件名不变） |

**净结论**：新增文件仅 4 类 6 项（rules.md、rules-governance.jsonl、shaping 两件、candidates 目录）；其余 13 项为沿用或向后兼容扩展；唯一行格式重定义是 craft-guard.md 审计行（第 3 节列破坏性）。

### 2.2 校验器逐项清单（G8 新增 + G9-G12 首版机器面 vs 协议面 + 两项迁移）

| 门禁 | 落点（文件） | 首版机器面 | 首版协议面 | 变更类型 |
| --- | --- | --- | --- | --- |
| G1 | `packages/design-playbook/scripts/g1_spec.py` | 既有 L1-L6 标题 + GWT 词序；**新增**：L2-L5 结构化字段块存在性、每页五态完整性（初始/加载/成功/失败/空逐页可枚举）、每 AC 有可达路径（L6 ↔ 路径表引用闭合） | 「哪条路径最重要」不判 | **深化**（收紧仅对新 run 生效） |
| G2-G4 | `g2_g4_pointback.py` | 消费面**零改动**（四字段 finding / 每 L6 恰一行 / closure / verdict——附加字段行被解析器自然忽略） | 附加字段（track/severity/confidence/disposition/assumes/rule:/dd:）由技能协议产出 | 零改动 |
| G5 | `g5_preview.py` | 零改动（E 档搭乘时天然覆盖） | — | 零改动 |
| G6 | `g6_evidence.py` 群 | 零改动（方法语义键为可选键，G6 不校验其内容——绑定与 capture contract 契约原样） | 方法语义五键由 orchestrator 绑定时写入（协议） | 零改动（切片 3 可选加键形状校验） |
| G7 | `g7_contract_drift.py` | 零改动（会话投影走既有函数序，无绕行通道——#28 5.2） | — | 零改动 |
| **G8** | `scripts/validate.py`（产品级，重写现行检测器契约段） | 产品级完整自校验：ID 唯一合格式、version 单调、枚举合法（status/authority/provenance/severity-default/check-type/executes-in/capability-domain）、owner 双跳值域（第一跳 ∈ 回流映射八工件 ∪ 绑定基线，第二跳 ∈ R1-R5）、related/overrides/supersedes 引用存在且覆盖图无环、machine-enforced 条目必有治理日志裁决引用 + 六条标准记录、placeholder 条目必有适用谓词与 blocked 出口、内容 lint（外部产品名与第三方规则原文禁令） | — | **新增** |
| G8（run 级） | `validate_run.py`（延后机器化，随切片 3） | 首版**协议消费**：技能保证「适用谓词求值为 applicable 的 advisory 条目恰一行、七列合法」 | 首版即协议；机器化切片 3 | 分层 |
| **G9** | `validate_run.py` 新模块（**`g9_shaping.py`**，决议 Q8=A：独立 gate 模块编排进 validate_run.py，与 g1/g5/g6 模块化先例一致） | 会话存在时：shaping-log 事件枚举合法、投影记录存在（决定 id ↔ 契约字段 ↔ spec 段映射行）、open=0 与 assumed 全 ack（复用 bind_first 既有面）、G1/G7 干净 | S6 条件 c 的「来源可追溯」语义（半机器） | **新增** |
| **G10** | `validate_run.py` 新模块（`g10_decisions.py`，切片 2） | 存在 DD 条目块时：id 唯一合格式、tier/status 枚举、E 档必有 confirmation（preview 在场必含事务 decision_id）、supersedes/rules 引用存在（rules 引用与 G8 注册表交叉）、R 档必有 selection.rationale | 比较矩阵内容质量、trade-off 充分性 | **新增** |
| **G11** | `validate_run.py` 新模块（`g11_coverage.py`） | point-back.md 含 Coverage statement 块且「必审完成状态 + 显式未审清单」两个子结构存在（存在性，不判内容） | 覆盖真实性、采样理由 | **新增** |
| **G12** | 首版协议（`validate_run.py` 机器化切片 4） | 首版**协议消费**：评审时代理按 1.2 判据表核对 + E1-E5 纠偏信号；契约面由 G7 既有漂移检测兜底 | 判据表核对、升档纠偏 | 分层（机器化 = diff 面机械判定，切片 4） |

**severity 别名迁移**（#29-Q1 移交本工单落地）：

- 新值域：`S3 | S2 | S1 | S0`（+ 事实/判断类别标注）；旧值 `high (blocking) | high | med | low` 保留为**兼容别名**。
- 换算表：`high (blocking)`→S3；`high`→S2；`med`/`low`→S1；S0 无旧值（新增）。
- 机器面现状：G2 只校验 finding 四字段存在性、不校验 severity 值域——别名期天然兼容；vNext 落码时 G2 扩展值域校验为「新旧并集」，移除期后仅收新值（**决议 Q5=B：别名期两个 minor——S1（v0.15.0）引入新值与并集校验，S3 末移除旧值**）。
- 处置轴 `disposition: blocking|advisory|info` 为 finding 附加字段行（解析器忽略旧版无此行的块，向后兼容）。

**craft-guard 七列改造对 validate.py 与 fixture 的影响**（#30 6.3 清单的落码面）：

1. `scripts/validate.py`：现行「Craft detector protocol」段（detectors.md 六字段块逐条校验 + saas-dashboard 六列正则 + composition/landing 八列正则 + brand 断言）整体重写为「Registry entries (G8)」段——消费 rules.md 条目块 + 七列 fixture 行形状正则 + 保留 brand 断言（已验证基线胜过通用检测器审美）。
2. 四份 fixture（`examples/craft-detectors/saas-dashboard.md`、`composition-contrast.md`、`landing-product-contrast.md`、`existing-brand-contrast.md`）：统一改七列并补 Applicability 演示（各含 not-applicable 附理由与 blocked 至少一处；现行 CRAFT-08 blocked 行改 `Applicability: blocked`）。
3. `tests/test_validate.py`：检测器段断言同步迁移（含 CI 面不变——仍经 `scripts/validate.py` 入口）。
4. `stages.py`、G2-G4/G6/G7：零改动（检测器行不在其消费面）。

---

## 3. 兼容边界（对已发布面 v0.14.1 的变更分类）

| # | 已发布面 | 变更 | 分类 | 迁移策略 | 废弃期建议 |
| --- | --- | --- | --- | --- | --- |
| 1 | 契约 v1（contract.json / decisions.jsonl / bind_first / G7 / contract-bind.json） | 零 schema 改动；会话经既有函数序投影 | **零破坏** | 无需迁移（#28 5.1：新增的是文件不是 schema 变更） | — |
| 2 | point-back.md 机器面（四字段 finding / 四字段 ledger 行 / closure 行 / verdict 两值 / G2-G4 消费） | 六块扩展 + 附加字段行 + invalidated 块 | **非破坏（additive）** | 现有解析器自然容忍新块与新行；旧格式报告在 vNext 下仍过 G2-G4 | — |
| 3 | evidence/manifest.jsonl | 方法语义五可选键 | **非破坏（append-only 可选键）** | 旧读取方忽略未知键（与 capture contract 同一兼容哲学）；旧条目无键 = 无方法语义，消费方按缺省处理 | — |
| 4 | decision-report.md 顶块（Fill 消费面） | DD 条目块追加其后 | **非破坏（顶块逐字保留）** | Fill/preview/report_ref 消费零改动；G5 语义不变 | — |
| 5 | spec.md 六层 + G1 | L2-L5 结构化字段 + G1 深化 | **非破坏（门禁收紧类）** | 仅对 vNext 起的 run 生效；历史 run 工件不重写不复检（run 门禁本就只跑当轮）；旧模板 spec 在 vNext 新 run 中复用需补结构化字段——技能起草时自动补 | 发布说明标注「G1 收紧」 |
| 6 | plan.md | run-profile 块必写 | **非破坏（新必填块）** | 仅 vNext 起的 run；旧 run 无此块不被复检 | 发布说明标注 |
| 7 | run-review JSON 契约面 / aggregate_runs.py | 候选队列派生视图（新可选键/节） | **非破坏（additive）** | 报告头 `run-review/v1` 保留；既有键零改动 | — |
| 8 | run_status.py 输出 | 新工件识别叙述行 | **非破坏（additive）** | 既有叙述原样 | — |
| 9 | **craft-guard 检测器表**（detectors.md 六字段块 + craft-guard.md 审计行 + validate.py fixture 段 + ui-evaluator 消费段措辞） | 列结构变化（Status 拆 Applicability/Result）、N/A 语义迁移（并入三态）、注册表迁址 | **破坏性（BREAKING）** | 单一切片内原子切换：rules.md + 薄引用层 + SKILL 七列 + 四 fixture + validate.py 重写 + ui-evaluator 措辞同批落码（G8 产品级同批上线，防中间态）；历史 run 的 craft-guard.md 不重写（append-only 哲学，新格式自迁移后 run 生效）；CRAFT-01…08 ID 零破坏（fixture 与历史引用可解析） | **决议 Q4=A：无双格式期**——S1 内原子切换，release note 标 breaking；旧写法在新格式下不再合法（#30 6.2 既定） |
| 10 | severity 旧值（`high (blocking)\|high\|med\|low`） | 分轴 S3-S0 + 兼容别名 | **非破坏 → 破坏（两段式）** | 别名期：G2 值域校验收新旧并集，消费方按换算表解释；移除期：旧值报结构错误 | **决议 Q5=B：别名期两个 minor**——S1（v0.15.0）引入、S3 末移除 |
| 11 | 命令签名（6 命令） | 无变化（仅描述更新） | **零破坏** | 无 | — |
| 12 | stage registry / stages.py | 零改动 | **零破坏** | 无 | — |
| 13 | npm 发布组与 release transaction | 延续锁步组（design-playbook + dsh-design-playbook 同版本） | **零破坏** | vNext 切片逐个过既有 release transaction；stable main 政策不变 | **决议 Q3=A：逐切片 minor**——v0.15.0=S1（含 breaking 标注）→ v0.20.0=S6；v1.0 留给外部用户信号后的语义化里程碑 |

**破坏点汇总（仅两处）**：craft-guard 检测器表（#9，硬切换）；severity 旧值（#10，两段式）。其余全部零破坏或 additive。

---

## 4. 可选面边界（vNext 保持可选的能力与降级行为）

原则（#31-Q6 / #24 全局原则 4 一致）：**协议不因适配器缺席而降级**——缺席 = 显式 `blocked` / `not-applicable` 记录或既有通道回落，永不静默跳过、永不臆断 pass。

| 可选件 | 缺席时的降级行为 | 记录载体 |
| --- | --- | --- |
| preview 适配器（`preview_prototype`，bundled 但宿主可能无 MCP） | E 档确认回落到 DD 条目 confirmation 块（kind: user + 呈批上下文引用）；G5 条件不触发但**必须记录**（run-profile 跳过清单一行） | run-profile 跳过清单；DD confirmation.via |
| capture provider（`execute_capture_plan`） | 必备证据不可得 → ledger `result: blocked`（「没测」≠「测了不行」）；G6 不触发；blocked 阻 Pass，回流 R5 | ledger blocked 行；Coverage statement 覆盖缺口 |
| 设计候选 provider 适配器（匿名数据契约） | 候选三通道退化为代理生成 + 用户带入，比较与记录义务不变 | DD 条目 candidates[].source |
| 非 Web 自动验证适配器（native 桌面等） | vNext 不交付；native-craft 声明层照常产出；Web 是首个且唯一自动验证面（地图 Out of scope 既定） | — |
| 学习闭环执行（晋升闭环） | 协议定义不执行（#24-Q6=B）：候选队列只派生呈报，裁决/晋升/回归验证全部人工；计数永不自动改规则、永不自动改严重度 | rules-governance.jsonl（仅用户事件） |
| 占位横切规则（I18N/PERF/SEC） | 谓词求值 not-applicable（附理由）/ blocked（证据不可得），永不静默跳过；占位不降低权威主张 | craft-guard.md 审计行 / Coverage statement 横切行 |

---

## 5. 首个 Web 验证切片（first Web validation slice）

### 5.1 切片组合（从 #32 留下的四个候选中选取）

#32 四候选：G12 机器化、craft-guard 迁移落码、run-profile 块落码、成形会话工件落码。

**决议组合（Q1=A，2026-08-14）：craft-guard 迁移落码 + run-profile 块落码 + 成形会话工件落码（三项），G12 机器化排除**（#32-Q6=A 已定 G12 首版协议消费，G7 兜底契约面；机器化留切片 4）。

理由：三项合起来恰好构成「跑通一次 **P2 标准 run**」的最小必需集——P2 必经 LR1 定档（run-profile）、LR2 成形（会话工件 + G9）、LR6 工艺（注册表七列 + G8）、LR8 评审（六块 + G11）；而 G12 的协议面足以支撑首切片（档位呈报与跳过记录是协议行为，机器复盘可后补）。

### 5.2 切片范围

- **工件**：rules.md（13 条起步）、rules-governance.jsonl（schema 定义）、shaping-log.jsonl + queue.json、plan.md run-profile 块、craft-guard.md 七列行、spec.md L2-L5 结构化字段、point-back.md 六块 + invalidated 块 + finding 附加字段行。
- **门禁**：G8 产品级（validate.py 重写）、G9、G11、G1 深化、G12 协议面；G2-G4/G5/G6/G7 既有零改动（G5 本切片不触发——无 E 档）。
- **命令**：无新命令；`/design-io`、`/ux-spec`、`/ui-review` 描述更新。
- **不含**（后续切片）：DD 条目块与 G10（P2 的 R/C 档仍产现行顶块，合法）、E 档与 preview 搭乘、manifest 方法语义键、G8 run 级机器化、G12 机器化、候选队列派生、severity 别名移除期、P3 全量档。

### 5.3 退出判据（全部机器可查，落现有 CI/validate 机制）

1. `python3 scripts/validate.py`：新「Registry entries (G8)」段全绿（13 条条目的枚举/引用/无环/占位谓词/内容 lint），四份迁移后 fixture 七列合法。
2. `python3 packages/design-playbook/tests/test_validate_run.py`（及 CI 全链）：对首切片 fixture run 跑通——G1 深化、G2-G4、G6、G7、G9、G11 全过，verdict 到达 Pass。
3. 新增单测（挂入 CI 既有步骤）：rules.md 条目解析、七列行解析、run-profile 块解析（tier/跳过清单）、shaping-log 事件枚举与 queue 派生、六块报告解析（新块存在性）、severity 新旧值并集校验。
4. 四份 craft fixture 各含至少一处 not-applicable（附理由）与一处 blocked 演示。
5. `run_status.py` 对 fixture run 的恢复叙述正确识别 run-profile 与 shaping 工件（挂 `tests/test_run_status.py`）。

### 5.4 验证方法（fixture run 演示场景）

沿用 #28-#32 贯穿示例「数据导出入口」的 **P2 标准走查**（决议 Q7=A：全新会话完整走查，含 S2 澄清与 CP 批次；loop-prototype 9.2）：成形 3 问 → CP-A/B/C 批次 → 投影（6 决定 + 4 assumed）→ G9 → spec 结构化字段 → R/C 档以现行顶块记录决策 → Fill → 注册表求值（craft 八条 + A11Y/RESP applicable，I18N/SEC not-applicable 附理由，PERF blocked）→ 采集（manifest 绑定）→ 双轨评审（1 条 a11y blocking S3 事实类 + 1 条 S2 advisory + 1 条 blocked 证据行）→ Recirculate → R4 修复 + invalidated 登记 → 重采重评 → closure → Pass。fixture 以静态工件（含合成 manifest/证据引用）入 `examples/` 或 tests fixture 目录，CI 经 `test_validate_run.py` 消费——不依赖 chromium（捕捉面由合成 artifact 覆盖）。

---

## 6. 交付切片与实现工单图（地图最后一条 Not yet specified 的答案）

vNext 全量落为 **6 个版本化切片**；切片 1 = 首验证切片。版本映射（决议 Q3=A）：**S1=v0.15.0（含 breaking 标注）→ S2=v0.16.0 → S3=v0.17.0 → S4=v0.18.0 → S5=v0.19.0 → S6=v0.20.0**（补丁号随需；v1.0 留给外部用户信号后的语义化里程碑）；每切片独立过既有 release transaction（stable main：main 始终等于最新正式发布）。实现工单按**决议 Q2=B** 执行：仅 S1 一张实现 issue 随本定稿创建，S2-S6 待 S1 落地验证后再建（边界可能随 S1 落码微调，#28-Q6 保留条件同款风险）。

| 切片 | 一句话范围 | 依赖 | 主要破坏面 |
| --- | --- | --- | --- |
| **S1** 首验证切片 | 注册表底座（rules.md + G8 产品级 + craft 七列迁移）+ run-profile 块 + 成形会话工件 + G9/G11/G1 深化 + 六块报告与 R4/R5 回流——跑通一次 P2 标准 run | 无（全部为新增或对现有面的扩展） | craft-guard 行格式（breaking，原子切换）；severity 别名期开启 |
| **S2** 设计决策深化 | DD 条目块 + G10 + R/C/E 三档全量 + preview 搭乘确认（G5 复用）+ candidates/ 引用层 + R3 重入（dd: 行 + supersedes）+ 基线 stale 三出口复核 | S1（rules 引用交叉、档位框架） | 无 |
| **S3** 证据与评审深化 | manifest 方法语义五键（含涉人证据 ethics 强制）+ 横切实条目执行面（A11Y/RESP 求值协议）+ 交互轨七维协议全量 + 五态×页面采样矩阵 + G8 run 级机器化 | S1 | 无（可选键 additive） |
| **S4** 回流状态机机器化 | 轮次机器计数（两轮停止）+ G12 机器化（diff 面机械判定）+ E1-E5 升档纠偏信号 + run-status 重入叙述 | S1（run-profile）；S2/S3 完成后全量生效 | 无 |
| **S5** 学习与治理 | D8 候选队列派生（run-review/aggregate additive）+ rules-governance.jsonl schema 落码 + 晋升协议执行准备（仍不自动晋升）+ severity 旧值别名移除期 | S1；S3（finding 附加字段面） | severity 旧值移除（breaking，两段式第二段） |
| **S6** P3 全量档与发布收敛 | P3 全链（CP-B 结构批次 / E 档双轮 preview / 构成变更与基线联动）+ 真 dogfood 验证 + README/文档/ADR 收敛 + vNext 版本定版发布 | S1-S5 | 视版本号策略（Q3） |

排序逻辑：S1 是底座与验证闭环；S2/S3/S4 相互独立、均只依赖 S1（可并行或换序）；S5 依赖 S3 的 finding 附加字段面；S6 收尾。每切片独立过既有 release transaction（stable main 政策：main 始终等于最新正式发布）。

---

## 7. 收尾核验（对照地图 Destination 逐句自查）

Destination 原文五要件：交互式需求成形、工具无关设计决策、双轨实现评审、证据门禁、回流；外部参考仅为研究输入。

| Destination 要件 | 产品表面落点 | 自查 |
| --- | --- | --- |
| 交互式需求成形 | ux-spec S0-S6 会话 + shaping 工件 + CP-A~E + G9（S1） | ✓ D1 有会话状态机、批次确认、投影与老化升级；契约零破坏 |
| 工具无关设计决策 | ui-picker R/C/E + DD 条目块 + provider 匿名数据契约 + 资产引用层 + G10（S2） | ✓ 协议不假设 named provider；预览/生成器均为可替换适配器 |
| 双轨实现评审 | ui-evaluator 三轨 + 横切适用性矩阵 + severity×confidence×处置分轴 + 六块报告 + G11（S1/S3） | ✓ 判断类 S3 永不 blocking；主观维度默认 advisory |
| 证据门禁 | G1-G12 全谱（既有 G1-G7 深化/沿用 + 新 G8-G12）+ manifest 方法语义 + 四层证据 | ✓ 机器面只证可证之事；implemented-UI pass 须绑定 rendered/interaction artifact |
| 回流 | R1-R5 两跳 + invalidated 最小失效集 + 12 类重入 + 轮次预算 + 升档纠偏（S1/S2/S4） | ✓ 失败定位 owning 声明层；blocking 不得删除通过 |
| 8 域全覆盖 | D1→S1；D2→S1（spec 结构化 + G1）；D3→S2；D4→S1/S3；D5→S1/S3；D6→S1/S2/S4；D7→S1（注册表 + G8）；D8→S5 | ✓ 每域有切片落点与工件/门禁 |
| 外部参考非依赖 | provenance 四值（benchmark-input-only 无规则解释权）+ G8 内容 lint + Provider 数据契约匿名化 | ✓ 注册表正文无外部产品名与第三方规则原文；外部样本不进运行时依赖 |
| 平台中立 / Web 首验证面 | 核心模型声明层平台无关；自动验证面仅 Web（capture provider）；非 Web 适配器出范围 | ✓ |
| 规划不实现 | 本轮零代码变更、零 GitHub 写操作（除认领）；切片图交付、工单创建留决策 | ✓ |

结论：八域全部有产品表面落点与切片归属；Destination 五要件 + 边界全部被覆盖。地图 Not yet specified 唯一剩余条目（版本化交付切片与实现工单图）由第 6 节回答。

---

## 8. 已确认决议（2026-08-14，用户裁决：8 项全部按建议采纳）

| 题 | 问题 | 决议 |
| --- | --- | --- |
| Q1 | 首验证切片组合 | **A**：craft-guard 迁移 + run-profile 块 + 成形会话工件（#32 三候选），以 P2 标准 run 为验证闭环；G12 机器化排除（首版协议消费，G7 兜底） |
| Q2 | 实现工单是否现在创建 | **B**：只建 S1 一张实现 issue；S2-S6 待 S1 落地验证后再建（避免工单图过早固化） |
| Q3 | 版本号策略 | **A**：逐切片 minor 发布——v0.15.0=S1（含 breaking 标注）→ v0.20.0=S6；延续 stable main + release transaction；v1.0 留给外部用户信号后的语义化里程碑 |
| Q4 | craft-guard 破坏性变更的废弃期 | **A**：无双格式期——S1 内原子切换（注册表 + 七列 + fixture + validate.py 同批），release note 标 breaking；历史 run 工件不重写 |
| Q5 | severity 旧值兼容别名期长度 | **B**：两个 minor——S1（v0.15.0）引入新值 + 别名并集校验，S3（v0.17.0）末移除旧值 |
| Q6 | 命令面是否新增入口 | **A**：不新增——成形会话经 `/design-io` 与 `/ux-spec` 深化进入；日后高频「单开会话」需求出现再增（additive 无破坏） |
| Q7 | 首切片 fixture 场景 | **A**：全新会话 P2——「数据导出入口」完整走查（S0-S6 + 一轮 Recirculate），含 S2 澄清与 CP 批次 |
| Q8 | G9 落点 | **A**：独立 gate 模块 `g9_shaping.py`（与 g1/g5/g6 模块化先例一致），编排进 `validate_run.py` |
