# 端到端闭环工件、门禁与回流状态机原型（End-to-end loop: artifacts, gates & recirculation state machine — decision model prototype）

- 工单：#32（wayfinder:grilling）。域：跨域集成——以 D6 回流 RC（Point-back repair & re-validation）为骨架，串接 D1 成形、D2 建模、D3 设计决策、D4/D5 评审与证据、D7 规则治理、D8 跨运行学习。
- 状态：**已定稿**。2026-08-14 用户裁决：8 项待决问题全部按建议采纳（Q1-Q8，见文末「已确认决议」）；正文按决议收敛表述。
- 性质：纸面决策模型（规划型地图产物）。不实现产品代码、不改技能与脚本；schema 落码归 #33 切片。
- 上游锁定决议（不可推翻，只集成）：#24 矩阵定稿（8 域、全局原则、决议 Q2/Q3/Q5/Q7/Q8）；#28 成形定稿（S0-S6 状态机、CP-A~E、会话生命周期 alive→archived→discardable、契约 v1 零破坏扩展、路径词表）；#29 评审定稿（双轨+横切、三级覆盖、四层证据、severity/disposition 分轴、六块报告、R1-R5 路由、最小失效集、方法语义 manifest 可选键）；#30 规则治理定稿（rules.md 注册表 + 20 字段 schema + G8 自校验、双层豁免、rules-governance.jsonl、晋升门槛 3 run·2 语境·0 误报）；#31 设计决策定稿（R/C/E 三档、DD 条目版本化块、双轨持久化、R3 supersedes 重入、基线漂移三出口）。
- **首要议题（地图 Not yet specified 耗时关切）**：run 分级档位（tiered run profiles）——流程重量与变更后果成正比。第 1 节是该关切的正面回应；第 9 节以三档走查量化呈现比例关系。

---

## 0. 真实落点基础（状态机必须落到的既有文件与机制）

状态机不发明新管线，只在既有管线上加档位与循环语义。全部落点来自已交付代码：

- **stage registry（`packages/design-playbook/scripts/stages.py`，ADR-0021）**：十段流水线 `baseline / reference / spec / plan / decision / preview / fill / craft / evidence / accept`；固定工件名 `spec.md`、`plan.md`、`decision-report.md`、`craft-guard.md`、`evidence/manifest.jsonl`、`point-back.md`、`filled-ui.*`、`design-baseline/state.json`。**run 级状态持久化 = 工件本身**（`run_status.py` 从工件存在性 + verdict 派生状态与恢复叙述）——状态机是该派生逻辑的概念层，不新增状态存储。
- **门禁现状（`validate_run.py` 编排）**：G1 spec 形状（`g1_spec.py`：L1-L6 齐全 + L6 逐条 Given/When/Then）；G2 证据行/finding 结构（`g2_g4_pointback.py`：每 L6 恰一行、finding 四字段）；G3 verdict 挣得（恰一 `Pass|Recirculate`；Pass 需全 pass）；G4 closure 覆盖（每 blocking 恰一 closure 行，不得删除通过）；G5 preview 确认（条件：preview 发生时 confirm-round 完整）；G6 证据绑定（条件：ledger 引用 `evidence/` 工件时 manifest 绑定）；G7 契约漂移（`g7_contract_drift.py`：bind 快照哈希一致）。G8 已被 #30 占用（注册表自校验，产品级 + run 级延后至本工单）。
- **回流两跳**：第一跳 observable → 声明工件（`ui-evaluator/SKILL.md` 权威表：spec/domain/craft/design/components/template/native-craft/reference/绑定基线）；第二跳声明工件 → R1-R5（#29 §8：requirement / interaction model / design decision / implementation / evidence plan）。repair map（`ui-evaluator/references/repair.md`）：最小 owning 声明 + 受影响证据 + 证据新鲜度规则（Fill 变化失效绑定证据、最新 manifest 条目胜、被取代引用出 warning）。
- **两轮停止策略（orchestrator SKILL.md 既有语义）**：「同一 blocking 发现经两轮 repair → re-evaluate 仍无新证据 → 停止回流并报告」。现为代理执行；本工单把它落为状态机轮次计数。
- **blocking 处置权（ui-evaluator SKILL.md 既有语义）**：无用户在环时 blocking 保持 Recirculate 并请求决定；仅用户决定（改声明或改严重度/接受风险）后才可重评，最终 Pass 工件不含 blocking。
- **run 契约五控制**：Goal←spec L1；Success←L6；Evidence←L6+ledger；Stop←orchestrator（Pass / 最小缺失决定 / 证据或权威不可得 / 重复 blocker）；Confirm←orchestrator+用户。**档位声明将并入此表（第 1.4 节）**。
- **持久契约（`contract_v1.py`，ADR-0017）**：`contract.json`（schemaVersion 1、fields 三态、changelog）+ `decisions.jsonl`（append-only、supersedes）+ `bind_first`（open 恒阻断、assumed 逐 run ack、产出 `contract-bind.json` 快照）。
- **preview 事务（`mcp/preview/transaction.py`，ADR-0013）**：`decision-round-<n>.json` / `confirm-round-<n>.json`、outcome 含 `aborted`、G5 校验。
- **run 聚合（`scripts/aggregate_runs.py`，v0.9）**：归一化 repeat blocker 计数、JSON 契约面——D8 信号的既有派生面。
- **跳步叙述义务（orchestrator SKILL.md 既有规则）**：「跳过一步要说一行——步名 + 理由 + 如何启用」——档位跳过记录直接沿用此纪律，不是新发明。

---

## 1. Run 分级档位（tiered run profiles，首要议题）

### 1.1 三档定义

按**变更后果 × 声明触碰面**分三档（决议 Q1=A，2026-08-14）：

| 档 | 代码 | 中文 | 一句话定义 | 典型场景 |
| --- | --- | --- | --- | --- |
| **点修档** | **P1**（point-fix） | 微改轻量路径 | 单一 owning 层的 point-back 修复，不触碰任何 decided 契约字段、不新增判据、不做设计决策 | 修一条 blocking finding（如 a11y 名称缺失）、补一次失效证据重采、Fill 实现偏离修正 |
| **标准档** | **P2**（standard） | 基线内功能变更 | 在已确认产品意图与设计基线内新增/变更功能：新增 run 范围 L1 值与 `l6.cN` 判据、D2 建模、R/C 档设计决策、标准覆盖评审 | 新增数据导出入口类功能 |
| **全量档** | **P3**（full） | 跨声明/产品级变更 | 修订既有 decided 契约字段（supersedes）、结构性 IA/主路径替代（CP-B 类）、命中 E 档判据（识别度/构成变更）、或影响 ≥2 个既有声明域 | 产品方向调整、构成级重设计、跨功能域改造 |

三档共用同一条状态机与同一套工件格式——**档位差异只体现在「哪些环节走多深、哪些门禁触发、哪些工件产生」，不产生平行流程**。

### 1.2 判据（判据面尽量机器可查）

判据主轴是**声明触碰面**（触到哪层声明），辅轴是**发现分布**（blocking 数与路由分布）。机器可查面标注 ◆：

| 判据 | P1 点修 | P2 标准 | P3 全量 |
| --- | --- | --- | --- |
| ◆ 契约 decided 字段 | 不新增、不修订（bind 快照前后一致） | 只新增（`l6.cN` 新判据、`<domain>.*` 新字段），不与既有 decided 冲突 | 修订/推翻既有 decided（`supersedes` 既有决定 id），或新增/修订 `l1.*` 产品级字段 |
| ◆ spec 触碰 | 只读；仅允许 R2 行级补行（决议 Q3=A：L4 状态行/L5 五态行，diff 限定在已声明段内，无新增 L6 顶层项，G12 可查） | 全量起草或增量起草（六层） | 全量 + 结构性替代（IA/主路径经 CP-B） |
| ◆ blocking 发现 | ≤1 且单一 owning 层 | 不限 | 不限 |
| ◆ finding 路由分布 | 全部 R4/R5（+R2 行级） | 含 R1（新判据类）合法 | 含 R1（证伪/修订类）、结构性 R2、R3 合法 |
| ◆ 设计决策档（#31） | 无（出现任何实质选择即升档） | R/C 档 | 含 E 档（#31 1.2 五判据任一命中即 P3 信号） |
| ◆ 成形会话 | 不开启（只做 bind 快速通道） | 标准 S0-S6（重复 run 走 S1 直达 S3 简化） | 全量 S0-S6 + CP-B 结构批次可能 |
| 评审覆盖（#29 三级） | 必审 = 失效集 + 相邻主路径；其余显式未审 | 必审 = 主路径 + 必需低频路径；采样按五态×页面矩阵 | 必审全量 + 采样矩阵完整执行 |
| 横切矩阵 | 适用谓词子集（触面相关家族） | 适用谓词全求值 | 适用谓词全求值 + 采样证据完整 |
| 学习信号 | 照记（轻） | 照记 | 照记 |

「机器可查」的实现形态：G7 + bind 快照 diff 覆盖契约面；spec/决策报告 diff 覆盖声明面；finding 的 track/route 附加字段覆盖发现分布；#31 E 档判据命中即 DD 条目 `tier: explore`。预判（受理时）靠代理核对，复盘（评审/终局时）靠门禁核对——两侧同一张表。

### 1.3 档位由谁判定

- **代理初判 + 用户确认一次**（决议 Q2=A）：LR1 定档状态中，代理按 1.2 表初判并在 run 契约 Confirm 控制中呈报（一项确认，不单开批次）；用户可改判。修复请求且判据明显时，档位确认可并入修复指令的回应，不额外打断。
- **升档自动、降档需用户**（Q2=A 锁定）：任何纠偏信号（1.5 节）出现时，代理**必须**立即升档并补走新增环节（安全方向，无需事先请示，事后一行记录）；降档（走得更轻）只能由用户改判——已走环节的超额履行合法（over-compliance 保留，不回退）。
- 依据：#24-Q7 决策权表「按后果分级」——档位是流程重量的选择，后果升级（改声明/接受风险）仍按 Q7 表归用户。

### 1.4 档位声明载体与跳过记录

- **载体：`plan.md` 头部 `run-profile` 结构化字段块**（决议 Q8=A；扩展既有编排 handoff 工件，不新增文件；字段块风格与 rules.md/DD 条目同族）：`tier: P1|P2|P3`、判据核对清单（1.2 各行的核对结果）、`confirmed_by: user + ts`、跳过项清单（步名 + 理由，沿用 orchestrator 既有跳步叙述义务）、升档事件（时间 + 触发信号 + 新档）。G12 档位门禁消费此块。**档位块必写**（Q8=A）：plan 步骤在现行管线中可选，run-profile 块本身对每个 run 强制——跳过其余 plan 内容合法，跳过档位块非法。
- run 契约五控制表扩展第六行：**Tier** | plan.md run-profile 块 | 档位 + 判据核对 + 跳过清单。

### 1.5 误判低档的纠偏（档位升降路径）

纠偏信号（出现任一即触发档位复核）：

| # | 信号 | 检出点 | 动作 |
| --- | --- | --- | --- |
| E1 | 评审出现 R1 发现（无主发现/判据不可判定/assumed 证伪） | LR8 | P1/P2 → 复核，涉既有 decided 修订则升 P3 |
| E2 | R2 结构性发现（路径断链/页面职责缺/决策点未建模），超出「行级补行」 | LR8 | 升 P2；涉 IA 替代则升 P3 |
| E3 | R3 发现挑战方向级决定，或 #31 E 档判据命中 | LR3/LR8 | 升 P3 |
| E4 | blocking 发现跨 ≥2 个 owning 层 | LR8 | P1 → P2 |
| E5 | G12 越界（实际声明触碰面 ⊄ 档位允许面） | LR8/LR10 | 升档至覆盖实际触碰面的最低档 |
| E6 | 用户改判 | 任意 | 任意方向；降档 = 超额履行保留 |

**纠偏动作语义**：升档**不废弃已产工件**——已走环节的产出全部保留，只补走新档要求而旧档未走的环节（如 P1→P2 补开成形增量会话并过 G9；P2→P3 补 E 档探索与用户确认、补全采样矩阵）。档位变更记入 run-profile 块（version bump 式追加一行），会话在档则同步记 shaping-log。

### 1.6 与域内既有轻量机制的衔接（映射表）

四个域内轻量机制不是被取代，而是成为档位体系的域内投影：

| 域内机制 | P1 | P2 | P3 |
| --- | --- | --- | --- |
| #28 成形问题上限（每批 ≤3、总数软上限 9、连续 2 批无新 T1 强制转假设） | 不开会话，无问题批次 | 全额适用；重复 run 走 S1 直达 S3 | 全额适用 + CP-B 结构批次 |
| #28 assumed ack（CP-E，逐 run） | bind 快速通道内执行 | 会话 S5 投影 + bind | 同 P2 |
| #29 覆盖三级（必审/采样/显式未审） | 必审=失效集+相邻主路径，其余显式未审 | 必审=主路径+必需低频，采样按矩阵 | 必审全量+采样完整 |
| #31 R/C/E 三档 | 不进决策环节 | R/C 档为主（E 判据命中即 E3 升档） | E 档完整（preview 搭乘 + G5） |
| #30 适用谓词三态 | 触面相关子集求值 | 全求值 | 全求值 |

---

## 2. 端到端状态机

### 2.1 主状态线（run 级）

两层结构：**run 级主线 LR0-LR10** + **域内子机**（成形 S0-S6、设计决策 R/C/E、回流修复 路由/修复/重评）。run 级状态的持久化即工件本身（第 0 节）；子机状态由各自工件（shaping-log、DD 条目、point-back invalidated/closure 块）承载。

```
LR0 INTAKE 受理
 │  入口：用户请求（新需求 / 修复请求 / 显式重跑）
 │  动作：逐字记录请求；装配输入（持久契约+决定日志 bind 预检、
 │        设计基线 state、既有 spec、参考契约、——修复请求时——上轮 point-back）
 │  出口：→ LR1（自动，无门禁）
 ▼
LR1 GRADE 定级定档（tier grading）
 │  动作：按 1.2 判据初判档位；P2/P3 时同时做 #28 S1 的 T1-T4 缺口/歧义/矛盾分级
 │        （run 档位分级与成形问题分级共用同一次扫描）；修复请求做轻量后果核对
 │  确认：档位呈报用户（Confirm 控制一项；可并入请求回应）
 │  出口：档位确认 → LR2；写 plan.md run-profile 块
 ▼
LR2 SHAPE 成形与建模（D1+D2）
 │  P1：BIND 快速通道——bind_first + assumed ack（CP-E）+ open=0 校验 + G7；
 │       不开成形会话、不产 shaping 工件
 │  P2/P3：S0-S6 子机（受理→分级→澄清→起草（含 D2 L2-L5 结构化字段起草）→
 │       批量确认（CP-A/B/C）→投影→出口判据）；P3 可含 CP-B 结构批次
 │  出口：P1 → LR5（跳过 LR3/LR4）；P2/P3 过 G9（S6 五条件）→ LR3
 ▼
LR3 DECIDE 设计决策（D3）
 │  子机：#31 R/C/E——P2 以 R/C 档为主（代理自主+记录）；P3 可 E 档
 │       （比较矩阵+用户确认）；R3 重入时按当时判据重新定档
 │  伴随：E 档决定改变 L2 region 职责 → spec 回写 + G1 复验；
 │        入口处 design-baseline verify（漂移 → DD 条目 stale → 三出口复核）
 │  出口：DD 条目完成（E 档过 G5 关联确认）→ LR4（在场且需要）或 LR5
 ▼
LR4 PREVIEW 预览确认（可选，适配器在场）
 │  子机：preview 事务 round_n；E 档确认搭乘（options=候选、G5 校验）
 │  出口：confirm 有效 → LR5；aborted → ABORTED（不得进 Fill，既有语义）
 ▼
LR5 IMPL 实现（Fill）
 │  动作：按 decision-report 顶块 + spec 语义实现；Re-Fill 信号
 │       （preview 修订报告后必须重 Fill 或记录用户接受——既有语义）
 │  出口：Fill 产物 → LR6
 ▼
LR6 CRAFT 工艺审计（craft-guard → 注册表执行）
 │  动作：按档位求值注册表适用谓词子集，产七列审计行（#30 迁移格式）；
 │       blocked 行带入评审作 craft proof gap
 │  出口：审计行齐全（G8 run 级）→ LR7
 ▼
LR7 OBSERVE 证据采集（可选，适配器在场）
 │  动作：capture plan 派生（L6 Given/When→state+actions）；provider 产工件；
 │        orchestrator 绑 manifest + 方法语义五键；provider 缺席 → blocked 证据行
 │  出口：证据面齐（重入时=失效集重采完成）→ LR8
 ▼
LR8 REVIEW 评审（D4/D5 双轨+横切）
 │  动作：产品轨逐 L6 判定、交互轨七维走查、横切适用性矩阵求值；
 │        六块报告（ledger/findings/positive/coverage/limitations/verdict）；
 │        判断类 S3 进「待用户裁决」子块（escalation 通道）
 │  出口：0 blocking 且全 pass → LR10（记 Pass）；
 │        存在 blocking/blocked → LR9；待裁决项 → WAIT-USER 后回 LR8
 ▼
LR9 REPAIR 回流修复（D6 子机：路由→修复→重评）
 │  PB1 路由：两跳（observable→声明工件→R1-R5），取最小 owning 集
 │  PB2 修复：最小修复指令（只修 owning 层）；R1/结构性 R2 → 转 LR1 档位复核；
 │        R3 → 转 LR3（DD supersedes）；声明类修订需用户确认（WAIT-USER）
 │  PB3 重评：失效集计算（`invalidated:` 块）+ 重采（LR7）+ 重评（LR8），
 │        只跑失效集 + 相邻主路径
 │  轮次计数：同一 blocking 发现两轮修复重评无新证据 → LR10（升级停止）
 │  出口：→ LR7（重采）/ LR8（直接重评）/ LR1 / LR3（跨层重入）
 ▼
LR10 VERDICT 终局
 │  动作：G3（verdict 挣得）+ G4（closure 覆盖）+ G12（档位复盘）；
 │        会话生命周期推进（archived → discardable 起点）；D8 信号派生（协议）
 │  出口：Pass → run 关闭；两轮停止 → WAIT-USER（blocking 处置三选一）
 ▼
终态：CLOSED-PASS ｜ ABORTED ｜（挂起态见 2.3）
```

### 2.2 迁移表（含所属环节与门禁）

| 迁移 | 触发 | 环节 | 门禁/条件 |
| --- | --- | --- | --- |
| LR0→LR1 | 输入装配完成 | 受理 | 无 |
| LR1→LR2 | 档位经用户确认 | 定档 | run-profile 块写入 |
| LR2→LR3 | G9 过（P2/P3） | 成形 | G9 + G1 + G7 |
| LR2→LR5 | P1 bind 快速通道完成 | 成形 | bind_first（open=0、assumed ack）+ G7 |
| LR3→LR4 | E 档且 preview 适配器在场 | 决策 | DD 条目（G10） |
| LR3→LR5 | R/C 档或 preview 缺席 | 决策 | G10（有 DD 条目时） |
| LR4→LR5 | confirm 有效 | 预览 | G5 |
| LR4→ABORTED | aborted=true | 预览 | 既有语义 |
| LR5→LR6 | Fill 产物 | 实现 | 无（Re-Fill 信号除外） |
| LR6→LR7 | 审计行齐全 | 工艺 | G8 run 级 |
| LR7→LR8 | 证据面齐 / blocked 行如实登记 | 采集 | G6 |
| LR8→LR10 | 0 blocking 且全 pass | 评审 | G2 + G10 + G11 |
| LR8→LR9 | 存在 blocking/blocked | 评审 | — |
| LR9→LR7 | R4/R5 修复需重采 | 回流 | invalidated 块登记 |
| LR9→LR8 | 声明/证据更新后直接重评 | 回流 | — |
| LR9→LR1 | R1 / 结构性 R2 / 跨层 blocking（纠偏信号） | 回流 | E1/E2/E4 |
| LR9→LR3 | R3 设计决策重入 | 回流 | `dd:` 行引用 |
| LR9→LR10 | 同一 blocking 两轮未消 | 回流 | 轮次计数（机器可查：closure/invalidated 轮次注记，首版协议；后续修订：S4 已机器化落码 `repair_rounds`，终态见 ADR-0029） |
| LR10→CLOSED | Pass 且 G3/G4/G12 过 | 终局 | — |
| 任意→WAIT-USER | 确认点/呈报/档位呈报/blocking 处置 | 横切 | — |
| 任意→SUSPENDED | 用户中断 | 横切 | 会话 `suspended` 事件 / run_status 恢复叙述 |

### 2.3 挂起、等待与中断（对齐会话生命周期）

- **WAIT-USER 等待用户**：不改变所处环节，只挂起等待（CP-A~E 批次、E 档确认、判断类 S3 呈报、blocking 处置、档位呈报）。响应走既有决定机制（decisions.jsonl / DD 确认块 / 治理日志 / run-profile），响应后回原状态。
- **SUSPENDED 中断**：任意状态可中断——成形会话内写 `suspended` 事件（#28 4.2 重放语义）；run 级恢复靠 `run_status.py` 从工件派生的 stage 叙述（既有机制，零新增）。无日历 TTL；过期仅由结构事件触发（同范围新 run / 契约漂移，#28 4.2 同款）。
- **会话生命周期窗口**：alive = LR2 进行中；archived = G9 过 → run 终局；discardable = run 终局且无未决 point-back 引用（#28 4.3 原样）。

---

## 3. 工件总清单（全 loop）

生命周期：**run 级**（随 run 归档可弃）/ **项目级**（跨 run 持久）/ **产品级**（随插件分发、run 只读）。标注「沿用/扩展/新增」与档位适用（产生/消费）。

| # | 工件（路径） | 生命周期 | 格式与 schema 来源 | 写入权威 | P1 | P2 | P3 | 处置 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `contract.json` | 项目级 | contract_v1（#28 §0；零破坏扩展结论 #28 5.1） | promote_fields/apply_decisions；decided 仅经用户确认 | 读 | 写（新增） | 写（新增+修订） | 沿用 |
| 2 | `decisions.jsonl` | 项目级 | contract_v1（append-only、supersedes） | append_decision（用户确认后） | 读 | 写 | 写 | 沿用 |
| 3 | `rules.md`（`skills/design-playbook/references/`） | 产品级 | #30 §1 20 字段 schema；G8 校验 | 产品发布流程；run 只读 | 读 | 读 | 读 | 新增（#30） |
| 4 | `rules-governance.jsonl` | 项目级 | #30 §5.3 事件 schema | 仅用户决定性事件 | 读 | 读 | 读 | 新增（#30） |
| 5 | `<project-root>/DESIGN.md` + `.scratch/<run>/design-baseline/state.json` | 项目级 / run 级 | design-baseline v1（ADR-0012） | design_baseline.confirm（显式批准） | 读 | 读 | 写（构成变更时） | 沿用 |
| 6 | `.scratch/<run>/spec.md` | run 级 | ux-spec 六层 + L2-L5 结构化字段（#24-Q2，schema 本工单移交 #33 落码） | 成形投影（S5）；DD 回写（region 职责） | 读+行级补 | 写 | 写 | 扩展 |
| 7 | `.scratch/<run>/plan.md`（含 run-profile 块） | run 级 | 编排 handoff + 本工单 run-profile 字段块 | orchestrator；档位行经用户确认 | 写 | 写 | 写（含升档事件） | 扩展 |
| 8 | `.scratch/<run>/shaping/shaping-log.jsonl` | run 级（archived 后只读） | #28 §4.1 事件枚举 | 成形会话（代理事件流；confirmed 类事件对应用户裁决） | — | 写 | 写 | 新增（#28） |
| 9 | `.scratch/<run>/shaping/queue.json` | run 级（派生态） | #28 §4.1（可从 log 重建） | 派生 | — | 写 | 写 | 新增（#28） |
| 10 | `.scratch/<run>/decision-report.md`（顶块+DD 条目块） | run 级 | #31 §4.1 DD schema；顶块逐字保留 | ui-picker/编排；E 档确认经 preview 事务 | — | 写（R/C） | 写（含 E） | 扩展 |
| 11 | `.scratch/<run>/preview/decision-round-<n>.json`、`confirm-round-<n>.json` | run 级 | preview 事务 v1（ADR-0013） | 事务（决定权与持久化） | — | 可选 | 写（E 档） | 沿用 |
| 12 | `.scratch/<run>/candidates/` | run 级（可弃引用层） | #31 §5.2 path+sha256 | 编排（provider 适配器产工件） | — | — | 写 | 新增（#31） |
| 13 | `.scratch/<run>/filled-ui.html/.md` | run 级 | Fill 产物 | Fill | 写 | 写 | 写 | 沿用 |
| 14 | `.scratch/<run>/craft-guard.md` | run 级 | #30 §6.2 七列审计行 | craft-guard 执行（advisory 记录） | 写（子集） | 写 | 写 | 扩展 |
| 15 | `.scratch/<run>/evidence/manifest.jsonl` | run 级（append-only） | manifest v1 + 方法语义五可选键（#29-Q6） | orchestrator（provider 永不写） | 写（重采） | 写 | 写 | 扩展 |
| 16 | `.scratch/<run>/point-back.md` | run 级 | 六块报告 + `invalidated:` 块 + finding 附加字段（#29 §7/§8） | ui-evaluator/编排 | 写（重评面） | 写 | 写 | 扩展 |
| 17 | `.scratch/<run>/contract-bind.json` | run 级 | bind_first 快照（ADR-0017） | bind_first（每 run） | 写 | 写 | 写 | 沿用 |
| 18 | `.scratch/<run>/reference/contract.md` + `manifest.json` | run 级 | reference-intake v1（ADR-0011） | reference-intake | 条件 | 条件 | 条件 | 沿用 |
| 19 | stage registry（`stages.py`） | 产品级 | ADR-0021 | 产品发布流程 | — | — | — | 无改动（shaping/candidates 非 stage 标记；spec stage 标记仍为 spec.md） |

结论：**新增文件仅 4 类**（shaping 两件、rules 两件、candidates 目录；其中 rules/candidates 已由 #30/#31 定稿），本工单新增的只有 run-profile 块且落在既有 plan.md 内；其余全部为沿用或向后兼容扩展（附加字段行/可选键/追加块）。

> 补注（2026-08-15，#44）：Fill 面亦可落在宿主树而非 run 根——`plan.md` 可用 `fill: <path>` 字段行登记这些路径（run 根相对或宿主项目相对），`run_status.py` 据此在 `filled-ui.*` 之外判定 fill 段（第 19 行 stage registry 零改动）。

---

## 4. 统一门禁序列

G1-G8 沿用既有语义（G8 含 #30 的产品级 + 本工单承接的 run 级）；G9-G12 为本工单编排的新门禁（#29/#30/#31 均声明「编号由 #32 统一编排」）。

| 门禁 | 名称 | 执行时点 | 检查内容 | P1 | P2 | P3 | 失败时回流 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| G1 | spec 形状 | LR2 出口（spec 写后/回写后复验） | L1-L6 齐全 + L6 逐条 GWT（既有）+ 深化面：每页五态完整、每 AC 有可达路径（#24-Q2） | 复验（spec 未变则平凡通过） | ✓ | ✓ | LR2 |
| G2 | 证据行/finding 结构 | LR8 | 每 L6 恰一行；finding 四字段（+附加字段协议） | ✓ | ✓ | ✓ | LR8 内补结构 |
| G3 | verdict 挣得 | LR10 | 恰一 verdict；Pass 需全 pass + 零 blocking | ✓ | ✓ | ✓ | LR8 |
| G4 | closure 覆盖 | LR10 | 每 blocking 恰一 closure 行 | ✓ | ✓ | ✓ | LR9 |
| G5 | preview 确认 | LR4 后（条件：preview 发生） | confirm-round 完整（confirmed+floor_pass+report_ref 匹配） | — | 可选 | ✓（E 档在场） | LR4（重跑事务） |
| G6 | 证据绑定 | LR7/LR8 | 工件存在 + manifest 绑定同 criterion | ✓ | ✓ | ✓ | LR7 |
| G7 | 契约漂移 | LR2（bind）、声明修订后 | bind 快照/决定日志/归一化字段哈希一致 | ✓ | ✓ | ✓ | LR2（新契约重分级） |
| G8 | 注册表自校验 | 产品级（validate.py）+ run 级（LR6） | 产品级：条目完整/引用无环/枚举合法；run 级：applicable 条目恰一行、七列合法 | ✓（子集） | ✓ | ✓ | 产品级阻断发布；run 级回 LR6 |
| **G9** | 成形出口 | LR2 出口（条件：会话开启） | #28 S6 五条件（open=0、assumed 全 ack、L1+L6 可溯、G7 干净、G1 齐全） | —（无会话；bind 通道由 bind_first 自身阻断） | ✓ | ✓ | LR2 |
| **G10** | 设计决策条目 | LR3（条件：存在 DD 条目块） | id 唯一、tier/status 枚举、E 档必有确认（preview 在场必含事务 id）、supersedes/rules 引用存在、R 档必有 rationale | — | ✓ | ✓ | LR3 |
| **G11** | 覆盖声明 | LR8 | 必审完成状态 + 显式未审清单**存在性**（不判内容，#29-Q7） | ✓（重评面范围） | ✓ | ✓ | LR8 |
| **G12** | 档位边界 | LR8/LR10（纠偏复核点） | 实际声明触碰面 ⊆ 档位允许面（契约 diff 经 bind 快照、spec/报告 diff、路由分布）。**首版协议消费**（决议 Q6=A）：评审时代理按 1.2 判据表核对 + E1-E5 信号触发，契约面由 G7 既有漂移检测兜底；机器化随 #33 切片（后续修订：S4 已机器化落码 `g12_tier_boundary`，终态见 ADR-0029） | ✓ | ✓ | ✓ | LR1（升档纠偏，非豁免） |

要点：所有条件门禁（G5/G6/G9/G10）的「不触发」由档位或适配器缺席决定，且**必须记录**（run-profile 跳过清单 / orchestrator 既有跳步叙述一行）——静默跳过非法。G12 失败的出口是升档重走，不是豁免（第 6 节）。

---

## 5. 停止条件与 verdict 语义

### 5.1 run 的终点

| 终点 | 语义 | 进入条件 |
| --- | --- | --- |
| **CLOSED-PASS** | 正常关闭 | LR10：G3（零 blocking + 每 L6 恰一行全 pass）+ G4 + G11 + G12 |
| **Recirculate 闭环后 PASS** | 修复轮次走完后转 Pass | LR9→LR7/LR8→LR10 |
| **升级停止（escalated stop）** | 同一 blocking 两轮修复重评无新证据 → 停止回流、报告并请求决定（orchestrator 既有 Stop 语义的落位） | LR9 轮次计数 → LR10 → WAIT-USER：用户三选一（修订 owning 声明 / 接受风险并记录 / 维持挂起）；前两者可使 run 转为 Pass 关闭或显式接受关闭 |
| **ABORTED** | preview aborted 或用户显式中止 | 工件保留（append-only 哲学），不产生 verdict |

### 5.2 verdict 值域与档位的关系

- **值域沿用 `Pass | Recirculate` 不扩**（决议 Q4=A；G3/G4/verdict_syntax 消费面零改动）。「升级停止」「挂起」是 **run-status 叙述态**而非 verdict 值——与现行「point-back.md present — confirm ## Verdict, then stop or recirculate」的叙述层一致；终局事实可从 point-back 与 run-profile 机器派生，无需第三 verdict 值。
- **Pass 的门槛同构、范围声明不同**：三档的 Pass 都是「必审范围内全 pass + 零 blocking」，但范围由覆盖声明如实记录——P1 的 Pass 只对失效集+相邻主路径负责，报告限制声明必须写明（#29 L3/L4 既有义务），未审部分不产生 pass 贡献。
- **blocking 处置权与档位无关**：任何档位下，blocking 的豁免/降级都仅当用户改变声明或接受风险（#24-Q7；ui-evaluator 既有语义）。

### 5.3 挂起语义汇总

WAIT-USER（等待特定决定，决定后回原状态）/ SUSPENDED（中断，恢复靠工件派生叙述）/ 无日历 TTL（CONTEXT 既有 Avoid；过期仅由结构事件触发）。

---

## 6. 豁免规则统一

把 #30 的双层豁免推广为全门禁的**三分类处置**：

| 类别 | 覆盖对象 | 处置 | 记录载体 |
| --- | --- | --- | --- |
| **(a) 结构完整性门禁——不可豁免** | G1-G7 机器面、G9-G12 | 失败即回流修复，无豁免通道（豁免=伪造工件，fail-closed 哲学）；「不触发」只由条件语义（preview 未发生/无会话/无 DD 块）或档位矩阵决定（决议 Q5=A：豁免客体仅限规则命中，永不扩及门禁本身） | 条件不触发记 run-profile 跳过清单（一行理由） |
| **(b) 规则命中豁免——advisory 类** | 注册表 advisory 条目命中（含 craft 八条、占位三条） | 代理可记 **run 级豁免**：规则 `ID@version` + 可观察理由 + 证据引用；空白理由非法；随 run 归档失效 | 检测器七列行的 Exception check / point-back finding 块（#30 §1.3 原样） |
| **(c) 规则命中豁免——machine-enforced 类** | 晋升后的 machine-enforced 条目 | **仅用户**（=接受风险，#24-Q7）；无日历 TTL，仅结构事件触发复核（规则修订/被取代/所依声明变更） | `rules-governance.jsonl` 持久豁免事件 + 决定日志同步（field=规则 ID） |

- 统一原则：**豁免的客体是「规则命中」，不是「门禁」**；门禁本身只有「通过/失败/不触发」三态。这条边界防止「豁免 G4」式危险的语义漂移。
- S6/G9 的 open 处置（CP-D 解决/接受风险降级 assumed）是**机制内通道**，不算豁免；两轮停止后的接受风险走 blocking 处置（用户），同样不是门禁豁免。
- P1 特别说明：点修档跳过的环节（成形会话、设计决策、preview）属 (a) 的档位矩阵跳过，在 run-profile 块留痕，可被 G12 复盘。

---

## 7. 重入路径总图

### 7.1 重入事件总表（事件 → 起点 → 落点 → 失效集）

| # | 事件 | 起点 | 落点 | 失效集计算 |
| --- | --- | --- | --- | --- |
| W1 | R4 实现偏离 | LR8 | LR9→LR5（修 Fill）→LR7 重采→LR8 | 直接受影响 criterion + 其绑定工件（`invalidated:` 块） |
| W2 | R5 证据计划缺陷 | LR8 | LR9→LR7（修 capture/换 provider/补采）→LR8 | 缺陷 criterion 的证据行；实现与声明不动 |
| W3 | R2 行级补行（五态/状态行） | LR8 | LR9→LR2（spec 补行，P1 边界内）→LR8 | 命名该边缘的 criterion |
| W4 | R2 结构性（路径/职责/决策点） | LR8 | LR9→LR1（档位复核，E2 升档）→LR2 增量建模→LR8 | 受影响 L6 + 以其为来源链的派生项（#28 2.4 下游对应） |
| W5 | R1 无主发现/判据不可判定 | LR8 | LR9→LR1（E1 复核）→LR2 **重开成形子树**（新会话 superseded_by）→…→LR8 | #28 2.4 四层（字段→派生字段→spec 段→证据行） |
| W6 | R1 assumed 证伪（run 内/跨 run） | 任意（评审/后续观察/用户陈述） | 同 W5；证伪字段回 open，`supersedes` 修订 | 同上（最小子树，跨子树不动） |
| W7 | R3 方案假设失败/取舍未记录/基线冲突 | LR8 | LR9→LR3（新 DD 条目 supersedes 旧条目；按新判据重新定档）→（E 档则 LR4 新 round + G5）→spec 回写+G1→LR5 Re-Fill→LR7→LR8 | 被挑战 DD 条目（标 invalidated）+ 消费该方向的实现面 + 依赖其假设的 L6 证据 |
| W8 | 基线漂移（design_baseline.verify 检出） | LR3 入口 / 任意 verify 时点 | 引用旧 sha 的 DD 条目标 stale → 三出口：**保持**（复核行+新 sha，回原流程）/ **修订**（同 W7 路径）/ **升级呈报**（WAIT-USER，回到方向级=升 P3） | 修订时同 W7 |
| W9 | 成形会话子树重开 | 任意（W5/W6 触发） | 新会话只处理失效子树；已确认项不可变（supersedes 修订） | #28 2.4 |
| W10 | 档位纠偏升档 | LR8/LR10（E1-E5 信号） | LR1 重新定档→补走新增环节（已产工件保留） | 无证据失效（只有流程补差） |
| W11 | 规则修订/降级触发复核 | run 间（治理事件） | 历史不重写；持久豁免按结构事件复核；下一 run 起按新状态执行；machine-enforced 晋升后首个 run 须记录首条正式执行结果（#30 §5.4） | 无回溯失效（append-only 哲学） |
| W12 | preview 修订决策报告（Re-Fill 信号） | LR4 | LR5 必须重 Fill（或记录用户接受既有 Fill）后才可 observe*/评审——既有语义原样落位 | Fill 前的绑定证据（若已采） |

### 7.2 与最小失效集语义的统一

所有重入共用一条失效哲学（不因档位/事件类改变）；**跨层发现的修复顺序按声明层依赖序 R1→R2→R3→R4，evidence plan（R5）在任一层修复后随时追加**（决议 Q7=A——上游修订会使下游修复作废，按依赖序避免重复修复与二次失效）：

1. **失效范围可计算且取最小集**：直接受影响 criterion + 来源链派生项 + 绑定证据行；未受影响证据保留。
2. **表达载体统一**：`point-back.md` 的 `invalidated:` 块（#29 §8.2 schema）——W1-W8 全部落此一处，不另造失效登记。
3. **历史不可改写**：被取代工件走 overwrite/revision 命名，最新 manifest 条目胜；被取代引用出 warning（repair map 既有规则）；DD/决定/规则修订一律 supersedes 新条目。
4. **重评范围 = 失效集 + 相邻主路径**（D6 最小修复），轮次预算两轮（5.1）。

---

## 8. 跨运行学习挂钩（D8，协议定义不实现）

| 信号 | 派生点（状态） | 输入（既有面） | 协议（#30 §5） |
| --- | --- | --- | --- |
| repeat blocker / 重复发现 | LR10 后 run-review / aggregate_runs | 归一化 observed/issue 文本 + finding 附加字段（track/severity/confidence/evidence） | 候选资格：distinct runs ≥3 且任务语境 ≥2 且未解释误报=0 |
| assumed 老化计数 | LR2 bind（每 run ack 留痕于 contract-bind 快照） | 跨 run ack 历史 | 连续 2 run ack 未转 decided → 下次会话升 T1 必答（#28-Q1） |
| 判断类 S3 呈报响应 | LR8 待用户裁决子块 | 三选一动作记录 | 「提交晋升队列」→ candidate_opened 事件 |
| verdict 分布 × 档位 | LR10 + run-profile | 各档 verdict 结果、轮次数、升档事件 | **档位判据校准信号**——升档频繁的判据行送 D7 复核（耗时关切的反馈回路） |
| G12 越界频率 | LR8/LR10 | 越界事件（信号类别） | 判据漂移信号：某判据行频繁越界 → 修订档位判据表（用户裁决） |
| 晋升裁决 | 用户（任意时点） | 治理日志事件 | candidate_opened / adjudicated / exemption_*（#30 事件枚举） |

状态机侧的挂钩只有三个：LR2（ack 留痕）、LR8（呈报子块）、LR10（verdict 后聚合视图从 run 历史派生，不新增持久状态——#28 先例）。候选队列与晋升协议本体是 #30 已定稿的协议，闭环执行延后（#24-Q6=B）。

---

## 9. 三档走查示例

### 9.1 P1 点修档：修一条 blocking point-back

场景：上轮评审的 blocking finding「超限提示 toast 无可访问名称与 role=alert」（#29 §9.3），用户指令「修掉它」。

- **LR0**：受理修复请求；装配上轮 point-back.md（finding + invalidated 块）。
- **LR1**：初判 P1（单 blocking、R4 路由、零声明触碰——判据核对：bind 快照无 decided 变更预期、spec 只读、无决策环节）；档位确认并入指令回应。plan.md run-profile：tier P1 + 跳过清单（成形会话/设计决策/preview + 各一行理由）。
- **LR2 BIND**：bind_first；4 个 assumed 逐项 ack（CP-E 一批）；open=0；G7 干净。
- **LR5**：Fill 修 toast（role=alert + 可读名含超限数值）。
- **LR6**：注册表求值——触面为 toast 组件：3 条 applicable、5 条 not-applicable（附理由）、0 blocked；G8 run 级过。
- **LR7**：重采失效集 = L6.2 的 rendered + interaction 各一件（manifest 追加 2 条，方法语义键齐）。
- **LR8**：重评面 = L6.2 + 相邻主路径节点；coverage statement（必审=重评面、显式未审=其余全列）；ledger 更新 L6.2 行；G2/G11。
- **LR10**：closure 行闭合该 blocking（G4）；全 pass（G3）；G12 复盘（声明面未越界）→ **Pass**。
- 无 LR9（修复一次到位）、无成形会话、无 DD 条目、无 preview。

### 9.2 P2 标准档：基线内新增「数据导出入口」（#28/#29/#31 同例）

- **LR0→LR1**：新功能、基线内（新增 run 范围 L1 值 + `l6.c1/c2` 新判据 + `export.*` 假设字段；不改既有 decided）→ P2。
- **LR2**：S0 受理→S1 分级（3 问 T1）→S2 澄清→S3 起草（浮出 CP-B 入口 IA 两案）→S4（CP-A 4 项 / CP-B 1 项 / CP-C 3 项）→S5 投影（6 条决定 + 4 个 assumed）→S6 过 G9。shaping-log/queue 两工件。
- **LR3**：DD-0001（R 档：触发控件形态）+ DD-0002（C 档：文件命名两案取舍）——#31 幕一二；G10。
- **LR4**：跳过（无 E 档；adapter 叙述一行）。
- **LR5→LR6**：Fill；craft 八条全目录求值。
- **LR7**：observe 采集（manifest 约 5 条，含方法语义）。
- **LR8**：产品轨 c1 pass / c2 pass / c3 **blocked**（采集跨导航失败）；交互轨 2 条 advisory；横切 1 条 **blocking**（a11y）→ Recirculate。
- **LR9**：PB1 路由（blocking→R4；blocked→R5）→PB2 修复→PB3 失效集登记 + 重采 + 重评（LR7→LR8）。
- **LR10**：closure + 全 pass + G12 → **Pass**。会话 archived→discardable。

### 9.3 P3 全量档：导出升级为「全局数据任务中心」第一步（含构成变更、R3 重入、基线漂移）

- **LR0→LR1**：修订既有 decided（`l1.goal` supersedes）+ region 构成变更（E 档判据 2 命中）→ P3。
- **LR2**：全量成形；中途 `export.column_scope` 假设证伪（W6）→ 子树重开（新会话 superseded_by；D-0007 supersedes D-0004；D-0008 新增 boundaries 永不项）；CP-D 处置遗留 open 一项。
- **LR3**：E 档 DD-0003（行内进度 vs 全局状态区，provider 候选 B + candidates/ 资产引用）→ LR4 round 1 用户选 B（G5）；**R3 挑战**（切页返回状态丢失，W7）→ DD-0004 supersedes DD-0003 → round 2 再确认（G5）→ spec L2/L5 回写 + G1；入口处基线漂移检出（W8）→ 复核「保持」。
- **LR5**：Re-Fill 信号触发（报告被 round 2 修订，W12）→ 重 Fill。
- **LR6→LR7**：横切五条目全求值（a11y/resp applicable，i18n/sec not-applicable 附理由，perf blocked 登记）；采样矩阵完整采集。
- **LR8**：必审全量 + 采样；一条 R4 blocking → LR9 修复重评一轮闭合 → LR10：G3/G4/G12 → **Pass**；D8 派生（升档事件、假设证伪事件入聚合视图）。

### 9.4 三档量化对比（重量与后果成正比）

| 维度 | P1 点修 | P2 标准 | P3 全量 |
| --- | --- | --- | --- |
| 经过状态数（含重入计步） | **8**（LR0/1/2/5/6/7/8/10） | **12**（10 个不同状态 + LR7/LR8 各重入一次） | **15**（10 个不同状态 + LR3×2、LR4、LR7/LR8×2、LR9） |
| 门禁触发次数 | **9**（G1 复验、G2、G3、G4、G6、G7、G8run、G11、G12） | **14**（+G9、G10；G2/G3/G11 各×2） | **17**（全 12 门禁；G5×2、G2/G3/G11×2） |
| 产生/更新工件数 | **7**（plan、contract-bind、filled-ui、craft-guard、manifest+2、point-back） | **14**（+spec、shaping×2、decision-report、contract、decisions、manifest 5 条…） | **20**（+preview×4、candidates、DESIGN/state 联动、会话×2 次） |
| 用户确认批次 | **2**（档位、CP-E ack） | **5**（档位 + CP-A/B/C/E） | **9**（档位 + CP-A/B/C/D/E + E 档两轮 + 呈报/处置） |
| 成形问题数 | 0 | 3 | 3-6（含子树重开） |
| 修复轮次 | 0-1 | 1 | 1-2 |

（比例近似 1 : 1.5 : 2 于状态与门禁、1 : 2 : 3 于工件与确认——档位体系把耗时压在后果小的变更上。）

---

## 10. 对后续工单的接口

| 工单 | 本原型交出的接口 |
| --- | --- |
| #33 | 首切片建议：P1/P2 全量 + P3 的 E 档协议；首切片机器化候选——G12 档位门禁（本工单 Q6=A 定为首版协议消费）、craft-guard 七列迁移（#30 清单）、run-profile 块落码（Q8=A：档位块必写）；G9/G10/G11 机器化按 #29-Q7 分层节奏；stage registry 零改动结论 |
| #28/#29/#30/#31（回执） | G 编号已编排（G9-G12）；失效集表达统一到 invalidated 块；skip 记录统一到 run-profile；豁免三分类覆盖全部新门禁 |
| D8 后续 | 档位校准信号（verdict×档位、G12 越界频率）入候选派生面 |

---

## 已确认决议（2026-08-14，用户裁决：全部按建议采纳）

| 题 | 问题 | 决议 |
| --- | --- | --- |
| Q1 | 档位数量与判据主轴 | **A：三档 P1 点修 / P2 标准 / P3 全量**，判据主轴 = 声明触碰面（decided 字段是否被修订、是否新增判据、是否命中 E 档判据），辅轴 = 发现分布；判据大多机器可查，与 #24-Q7「按后果分级」同构 |
| Q2 | 档位判定权 | **A：代理初判 + 用户在 run 契约 Confirm 中确认一次；升档自动、降档需用户**——升档是安全方向不应等人；降档减少流程必须有责任人；修复类明显档位并入指令回应避免额外打断 |
| Q3 | P1 的声明触碰边界 | **A：允许 R2 行级补行**（L4 状态行 / L5 五态行，diff 限定已声明段、无新增 L6 顶层项，G12 可查）——五态小漏是最高频小修，纯零触碰规则会使轻量路径覆盖面骤减 |
| Q4 | verdict 值域是否扩展 | **A：维持 `Pass \| Recirculate` 两值**——升级停止/挂起由 run-status 叙述态承载；G3/G4/verdict_syntax/run_status 消费面零改动；终局事实从 point-back 与 run-profile 机器派生 |
| Q5 | 豁免统一的三分类边界 | **A：结构门禁（G1-G12）不可豁免，豁免客体仅限「规则命中」**——advisory 类代理 run 级、machine-enforced 类仅用户（#30 双层推广）；档位跳过与条件不触发走 run-profile 独立记录面 |
| Q6 | G12 档位边界门禁的机器化节奏 | **A：首版协议消费**（评审时代理按判据表核对 + E1-E5 信号触发），G7 既有漂移检测兜底契约面；机器化随 #33 切片——diff 面机械判定先让协议与纠偏路径定型 |
| Q7 | 重入修复的顺序语义 | **A：按声明层依赖序 R1→R2→R3→R4，R5 随时追加**——上游修订会使下游修复作废，按依赖序避免重复修复与二次失效 |
| Q8 | run-profile（档位声明）载体 | **A：`plan.md` 头部结构化字段块，档位块必写**——不新增文件；plan 本就是 run 级控制面，G12 有稳定消费点，跳过清单沿用 orchestrator 既有跳步叙述纪律；仅跳过档位块非法 |
