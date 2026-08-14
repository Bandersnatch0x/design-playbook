# 工具无关设计决策协议原型（Tool-neutral design decision protocol — decision model prototype）

- 工单：#31（wayfinder:grilling）。域：D3 设计决策 DD（Tool-neutral design decisions）。
- 状态：**已定稿**。2026-08-14 用户裁决：7 项待决问题全部按建议采纳（Q1-Q7，见文末「已确认决议」）；基线漂移复核三出口规则同日确认无异议。
- 性质：纸面决策模型（规划型地图产物）。不实现产品代码、不改技能与脚本；DD 条目正式 schema 与门禁机器化归 #32。
- 上游锁定决议（不可推翻，只细化）：#24 矩阵 8 域与全局原则（Provider 边界、证据两分、按后果分级的决策权表）；#24-Q7=A（改变识别度/构成的视觉方向→用户确认；已确认声明内的局部实现选择→代理自主）；#24 地图边界（不做设计工具替代、通用风格数据库、资产生成器；任何具名设计工具都不是运行依赖或规则权威——协议不假设 named provider，provider 是可替换适配器）；#28 成形定稿（T3 视觉方向只登记路由给 D3；CP-B 结构选择在成形内完成；确认批次语义；契约字段路径词表 `<layer>.<concept>` / `<domain>.*`）；#29 评审定稿（R3 回流目标 = design decision，触发特征 = 方案假设失败/取舍未记录/视觉方向与基线冲突；失效证据集；finding 附加字段行机制）；#30 规则治理定稿（authority 五级；advisory 规则可参与设计比较但规则不替选择；引用钉 `ID@version`）。
- 耗时关切约束（地图 Not yet specified）：流程重量须与变更后果成正比——基线内小选择不触发完整探索。本协议以**三档触发**（第 1 节）作为 D3 侧对该关切的回应；run 级分层执行轮廓归 #32。

本协议回答工单点名的六方面：方案提出（propose）、比较（compare）、确认（confirm）、记录（record）、交接（handoff）、重入（re-enter），外加走查示例。

## 0. 真实 schema 基础（协议的落点，全部来自已交付代码）

协议只落到已存在的字段名、文件名与函数，不发明平行体系：

- **decision-report.md（现行格式，`skills/ui-picker/SKILL.md` step 4；stage registry 固定工件名 `DECISION_REPORT`）**：顶块字段 `design-baseline: <binding.path> sha256:<digest> | waived:<reason>` / `scene:` / `density:` / `template:` / `regions:` / `components:` / `baseline-changes: none | <explicitly approved change>` / `risks:`。既有分支：「template 欠定时提出 2-3 个 IA 变体（同 spec、不同主区权重），各一行取舍，选一后完成 step 4」——这是本协议「轻量比较档」的既有雏形。
- **design-baseline（`skills/design-baseline/scripts/design_baseline.py`，ADR-0012）**：`prepare/confirm/verify` 三入口；`.scratch/<run>/design-baseline/state.json`（`schema: design-baseline/v1`）状态 `ready | needs_confirmation | waived | ambiguous`；`verify` 在 Fill 前重验基线哈希与来源新鲜度，下游只能消费刚通过 verify 的绑定；基线漂移是 craft 失败的 point-back 源。项目视觉权威 = `<project-root>/DESIGN.md`（兼容候选路径另议，不在本文命名）。
- **preview 决策事务（`mcp/preview/transaction.py`，ADR-0013）**：`run_preview_transaction(summary, round_n, report_ref, options, collect)`；绑定覆盖 `round / prototype_html_hash / report_ref / summary / options`；条目 `preview/decision-round-<n>.json` 含 `schema_version: 1`、生成 `decision_id`（uuid）、`binding`、`outcome{confirmed, user_confirmed, floor_pass, selected_options, feedback, anchors, aborted, rejected, …}`；确认工件 `preview/confirm-round-<n>.json` 含 `round / report_ref / confirmed / floor_pass / selected_options / feedback / timestamp / prototype_path / prototype_html_hash / decision_id`。事务拥有决定权与持久化；**G5** 校验确认工件完整性（confirmed=true + floor_pass + report_ref 匹配）。绑定里的 `options`（呈给用户的有序选项）与 `selected_options`（用户选择）正是 D3 方向确认可搭乘的既有接缝。
- **decisions.jsonl（`scripts/contract_v1.py`，ADR-0017）**：append-only，行 `{id, field, decision, rationale, confirmed_at, supersedes?}`，id 匹配 `^[A-Za-z0-9][A-Za-z0-9_.-]*$`；`decided` 只能由用户显式确认经 `append_decision` + `apply_decisions` 产生；G7 漂移校验。
- **回流两跳（#29 §8 + 现行 recirculate map）**：第一跳 observable → 声明工件（含 `design`）；第二跳 → R3（design decision）。finding 四字段保持稳定，附加字段行（如 `rule:`、`dd:`）被现有解析器忽略——向后兼容的引用通道。
- **规则注册表（#30 定稿）**：条目含 `authority`（hard-constraint > project-declaration > measured-threshold > platform-convention > advisory-aesthetic）、`applicability` 三态谓词、`severity-default`；引用钉 `ID@version`；G8 为注册表自校验门禁（产品级）。
- **#28 接口**：T3 视觉方向路由条目（open question → D3 决策报告输入）；契约字段路径词表；CP-B 确认批次语义（≤2 项、每项 ≤3 案、逐项原子、拒绝/改写语义、已确认项不可变）。

---

## 1. 方案提出（propose）

### 1.1 触发分级：三档，重量与后果成正比

对齐 Q7 决策权表与耗时关切，D3 的进入点不是「每次 ui-picker 都探索」，而是按后果分档（决议 Q1，2026-08-14：三档 R/C/E）：

| 档 | 代码 | 触发条件 | 决策权 | 记录义务 |
| --- | --- | --- | --- | --- |
| **直录档**（record） | R | 单一合理选择，或已确认声明内的局部实现（易混组件对解析、token 角色指派、文案微调、密度跟随基线） | 代理自主（Q7 第 4 行） | 一条极简 DD 条目：选择 + 一句理由 + 依据引用 |
| **轻量比较档**（compare） | C | 基线内存在 ≥2 个实质候选，但不命中任何 E 档判据 | 代理自主（同上）——档位只加深**记录**，不改变决策权 | DD 条目含候选 2-3 案 + 每案一行取舍 + 选择与拒绝理由 |
| **完整探索档**（explore） | E | 命中 1.2 任一判据 | **用户确认**（Q7 第 3 行） | 完整 DD 条目：问题、约束装配、候选（含 provenance）、比较矩阵、trade-off、选择/拒绝理由、确认记录 |

- R 档即现行 ui-picker done-when 的直落行为；C 档即现行「2-3 IA 变体分支」的正式化；E 档是本协议新增的结构化探索。三档共用同一记录载体（第 4 节），差别只在义务深度。
- **档位是记录与确认义务的分级，不是决策权的再分配**：C 档仍是代理自主；任何时点用户可把任何决定升级为亲自裁决（Q7 是默认表，用户保留全权）。
- **升降级**：C 档比较中途命中 E 判据 → 升 E（补齐矩阵与用户确认）；E 档被 R3 挑战后重开，重开后的新决定按当时判据重新定档。
- 反向保护：**基线内小选择永不触发完整探索**——E 档判据（1.2）全部以「识别度/构成/上游路由/回流挑战」为界，纯基线内选择最多落到 C 档。这是耗时关切在 D3 侧的硬承诺。

### 1.2 E 档触发判据（枚举，命中任一即 E）

1. **识别度变化**：候选将偏离已绑定基线（DESIGN.md，path+sha256 引用具体段落）声明的视觉角色、氛围、密度或 motion 约定——防静默品牌漂移（Q7 第 3 行门禁理由）。
2. **构成变化**：候选改变 template 骨架的 region 集合或权重分配（main/side/action/status 的重组），而非 region 内部填充。
3. **上游路由**：成形 T3 视觉方向 open question 条目到达（#28 接口——成形只登记不裁决）。
4. **回流挑战**：R3 finding 挑战既有决定的方案假设或未记录的取舍（#29 接口）。
5. **基线冲突**：候选与基线或硬约束规则冲突，需要显式取舍（对应报告 `baseline-changes ≠ none` 的情形）。

### 1.3 候选生成：数量与来源

- **数量**：E 档 2-3 案（有比较才有探索，下限 2；上限对齐 #28 CP-B 与现行 IA 变体分支）；C 档 2-3 案；R 档 1 案。
- **来源三通道，同权进入比较**：
  - **代理生成**（source: `agent`）：编排代理按约束起草；
  - **provider 适配器生成**（source: `provider-adapter`）：外部生成器经匿名适配器产出候选描述符（1.4）；
  - **用户带入**（source: `user`）：用户直接给出方向或草图——仍须走同一比较与记录（至少记录其与既有候选的差异陈述），防止绕过比较记录直接落稿。
- **provenance 义务**：每个候选必须记录 `source`、`created_at`；provider-adapter 候选附项目自定的匿名适配器句柄（如 `provider-a`），**永不记录具名产品**。协议绑定的只有决定与理由，不绑候选的产出方式。

### 1.4 provider 匿名接口（输入输出契约，不具名、不定义调用面）

协议不假设任何 named provider，也不定义工具名/传输面——任何能产出下述描述符的来源都合法。契约只在**数据形状**一层（决议 Q4，2026-08-14：数据契约级）：

```yaml
# 输入（编排 → provider 适配器）
question: <待决问题一句话>
constraints:
  baseline: {path, sha256, 摘引段落}      # 或 waived:<reason>
  spec: [l1.goal, l1.target_user, l6.c1…]  # 相关判据引用
  exclusions: [硬约束规则 ID@version…]     # 违规即排除的过滤器集
fidelity: description | wireframe | interactive-prototype   # 请求的保真度
budget: 2-3                                # 候选数上限

# 输出（provider 适配器 → 编排）
candidates:
  - label: <候选标签>
    summary: <一句话方向陈述>
    constraints_honored: <遵循声明>
    deviations: [对基线的偏离声明…]        # 有则必须显式，不得静默
    assets: [<path + sha256>…]             # 可选渲染工件，引用层（第 5.2 节）
    preference_note: <可选偏好注记>        # 无裁决力，仅 provenance
```

- provider 产出的是**候选描述符与工件**，不是证据、不是评分、不是选择——Provider 边界（CONTEXT）原样贯穿：provider 永不产出 evidence，永不发出 verdict。
- `deviations` 非空即提示 E 档判据 1/5 可能命中，编排必须复核档位。
- 适配器缺席时三通道退化为代理 + 用户，协议完整可用（预览与外部生成都是可选执行面）。

---

## 2. 比较（compare）

### 2.1 比较维度来源（三层，全部可引用）

| 层 | 内容 | 参与方式 |
| --- | --- | --- |
| **spec 目标层** | L1 目标用户/场景/非目标/L6 判据（`l1.*` / `l6.cN` 引用） | 任务适配轴：每案陈述其对目标用户任务的支持/不利（需人工判断——#24 D3 证据义务：方案哪个更适合任务需原型比较或用户证据） |
| **注册表规则层** | #30 注册表条目，按 authority 分流 | **硬约束**（hard-constraint）→ 候选排除过滤器：违规候选记排除理由，不进矩阵；**平台惯例/建议美学**（platform-convention / advisory-aesthetic，及适用时的 measured-threshold）→ 比较轴或每案注记；**项目声明**（project-declaration：契约/spec/基线）→ 装配进约束集，不是轴。**规则只提供轴与过滤器，永不替选择**（#30 锁定） |
| **基线约束层** | DESIGN.md 绑定（path+sha256）：视觉角色、密度、布局、motion、组件惯例 | 候选须声明遵循，或显式申请 `baseline-changes`（走 design-baseline 显式批准，见 4.3） |

- 规则引用一律钉 `ID@version`，写入 DD 条目的 `constraints.rules`；D3 消费注册表是**只读协议消费**（读 statement/authority/applicability），不执行检测器、不改 #30 的 `executes-in` 枚举——是否为 D3 增设执行面值留给 #32 评估。
- 适用谓词三态同样生效：`not-applicable`（附理由）的规则不进轴；`blocked`（证据不可得）的规则记为「该轴无法评估」，不得静默省略。

### 2.2 比较记录格式（维度 × 方案矩阵）

每轴一行，每候选一格，格内 = 支持或不利的**一句陈述 + 来源引用**：

```text
| 轴（来源）                      | 候选 A                  | 候选 B                  |
| 任务适配·导出中切页 (l1.scenes)  | 不利：状态散在行内       | 支持：全局一处可查       |
| 感知反馈相称性 (PERF-01@1)       | 部分：短导出足够         | 支持：长导出有进度感     |
| 基线·status region 惯例 (DESIGN.md §布局) | 未使用该 region | 启用该 region（遵循） |
```

### 2.3 不可公度时的呈现（trade-off 陈述，禁伪评分）

- 轴间不可公度是常态而非异常：矩阵呈现**事实与陈述**，不合成总分。**禁止数值评分、加权求和、排序分**——与 #29「报告不出现分数/评分，分数与清单是诊断不是验收」同一把尺子。
- 不可公度处显式写 trade-off 行：「A 以 X 换 Y」句式，落在 DD 条目 `comparison.tradeoffs`。
- 代理可给偏好建议（标注 `source: agent` 的 preference），但选择权按档位归属；E 档最终选择永远是用户。

---

## 3. 确认（confirm）

### 3.1 谁确认（对齐 Q7）

- **E 档 → 用户确认**：改变识别度/构成的视觉方向、上游 T3 路由项、R3 重开的方向修订。
- **R/C 档 → 代理自主 + 记录**：已确认声明（契约、spec、基线）内的局部选择，加审批是低价值摩擦（Q7 第 4 行门禁理由原文）。
- **基线修订 → design-baseline 显式批准**：任何 E 档决定若落地为基线变更（`baseline-changes ≠ none`），持久写入只能走 `design_baseline.confirm`（accept 流程原子写 DESIGN.md），报告侧联动记录；禁止从 DD 条目直写基线。

### 3.2 确认批次形态（沿用 #28 批量确认风格）

- E 档确认以**批次**呈报：每批 ≤2 项、每项 2-3 案（对齐 #28 CP-B 粒度上限）。
- 每项呈报内容：问题 + 比较矩阵 + trade-off 陈述 + **每案验收影响注记**（「选 A/B 分别影响哪些 `l6.cN` 与 L2 region 职责」——无下游影响的选择不配进 E 档，应降 C/R）。
- 逐项裁决：**确认 / 拒绝 / 改写**。

### 3.3 拒绝/改写语义（全档统一，沿用 #28）

- **批次内逐项原子**：同批已确认项不因他项被拒回退；部分确认合法。
- **拒绝**：该项携拒绝理由回到候选生成（只重生成该项，不重放整批）。
- **改写** = 拒绝 + 用户给定新候选：新候选 `source: user`，进同一比较与确认路径。
- **已确认项不可变**：修订只能经 DD 条目 `supersedes` 新条目（append-only 哲学贯穿到确认层）。

### 3.4 preview 搭乘语义（适配器在场时）

- preview 适配器在场且候选有可渲染形态时，E 档确认**搭乘既有事务**（决议 Q6，2026-08-14）：`options` = 候选标签有序列表，`report_ref` = decision-report.md 路径，`summary` = 问题一句话；用户经 preview 事务选择（confirm-round 的 `selected_options`）并留反馈（feedback floor 校验）；G5 校验确认工件完整性。
- DD 条目的 `confirmation.via` 记 `preview-round-<n>` 并链接事务 `decision_id`——确认 provenance 机器可查。
- **边界（#24 D3 锁定）**：preview 确认的是**方向选择**，不是最终实现验收——预览偏好不能自动提升为最终验收；实现是否满足判据仍归 L6 证据与评审。
- 适配器缺席时：确认记录直接落在 DD 条目 `confirmation` 块（kind: user + 时间戳 + 呈批上下文引用）；需要持久化的意图按 4.3 投影。

---

## 4. 记录（record）

### 4.1 设计决定条目 schema（DD 块）

载体 = 深化的 `decision-report.md`（stage registry 工件名不变；决议 Q2，2026-08-14）：现行顶块字段**逐字保留**（Fill 消费面不动），其后追加 DD 条目块（markdown 结构化字段块，与 #30 rules.md 同一可校验风格）。机器可查字段以 ◆ 标记：

```yaml
id: DD-0003 ◆                 # run 内唯一；跨 run 引用形如 <run>/DD-0003；
                              # 投影决定日志时兼容 id 正则
tier: explore ◆               # record | compare | explore
question: 导出进行中的状态呈现构成
status: confirmed-user ◆      # open | compared | confirmed-agent | confirmed-user
                              #   | superseded | invalidated
constraints: ◆
  baseline: DESIGN.md sha256:<digest>   # 或 waived:<reason>（沿用顶块语法）
  spec: [l1.scenes, l6.c1]
  rules: [PERF-01@1]          # 引用钉 ID@version，G8 注册表可交叉
candidates:
  - {id: A, source: agent, created_at: <ts>, fidelity: description,
     summary: 行内进度 + 工具列总进度, assets: []}
  - {id: B, source: provider-adapter, adapter: provider-a, created_at: <ts>,
     fidelity: sketch, summary: 全局状态区收纳导出任务,
     assets: ["candidates/B.html sha256:<digest>"]}
comparison:                   # C/E 档必填；R 档省略
  axes: [...]                 # 2.2 矩阵的序列化（轴来源引用 + 每案陈述）
  tradeoffs: "A 以上下文邻近换操作区占用；B 以全局可见换离上下文远"
selection: ◆
  candidate: B
  rationale: <选择理由，须回指轴或 trade-off>
  rejected: [{candidate: A, reason: <拒绝理由>}]   # E/C 档必填——拒绝理由与选择理由同等一等
confirmation: ◆               # E 档必填；R/C 档为 kind: agent
  kind: user | agent
  via: preview-round-1 decision_id:<uuid> | report-batch | agent-record
  confirmed_at: <ts>
  decision_log_id: D-0009     # 仅当已投影决定日志（4.3）
supersedes: null ◆            # 重入修订时指向被取代条目（引用存在性可查）
```

- **机器可查面**（首版协议消费，正式门禁归 #32——与 #29-Q7、#30-Q6 的分层一致；G 编号由 #32 统一编排，注册表侧 G8 已占用）：id 唯一且合格式；tier/status 枚举；E 档条目必有 `confirmation`（preview 在场时必含事务 decision_id）；`supersedes`/`rules` 引用存在；baseline sha256 格式；R 档条目必有 selection.rationale 一句。
- R 档极简形态：`id / tier / question / status: confirmed-agent / selection{candidate, rationale 一句} / constraints 引用`——直录不等于无记录，只是记录浅。

### 4.2 载体关系与无第三 SSOT 论证

| 事实类型 | 唯一可写权威 | 说明 |
| --- | --- | --- |
| run 内设计选择的出生与取舍 | decision-report.md 的 DD 条目 | run 级过程与决定记录；现行顶块是其摘要面 |
| 持久产品意图 | contract.json + decisions.jsonl | 零 schema 扩展（#28 同结论：路径自由字符串 + notes 足够）；只有用户确认可产生 decided |
| 持久视觉方向 | DESIGN.md（经 design-baseline confirm） | DD 条目永不直写基线 |
| 预览确认完整性 | preview 事务 + G5 | 不动（已决架构） |
| 交互模型呈现 | spec.md | 投影视图，非编辑面 |

- **扩展而非新载体**（工单第 4 项的结论）：深化 decision-report.md，不新增 design-decisions.jsonl 之类第三 SSOT；决定日志不承载 run 级设计取舍（它的 field 语义是产品意图，不是设计过程）。
- 交叉校验落既有机械面：G5（preview 确认完整性）、G7（投影后的契约漂移）、G8（rules 引用）、G1（spec 回写后复验）。

### 4.3 持久化投影（何时离开 run；决议 Q3，2026-08-14：双轨）

- **默认 run-scoped**：多数设计决定随 run 归档，DD 条目即全部记录。
- **投影决定日志**：仅当用户在确认时显式声明「此方向为项目约定」——`append_decision` 落一条（field 用 #28 Q6 词表 `<domain>.*`，如 `export.status_pattern`；id 兼容正则），条目回填 `decision_log_id`。代理不得自行投影。
- **投影基线**：仅当方向落地为视觉基线变更——走 `design_baseline.confirm` 显式批准，报告 `baseline-changes` 字段与 state.json decision 联动。
- **投影 spec**：E 档决定改变 L2 region 职责时，spec 相应段回写并重跑 G1（spec 是投影视图，决定是权威——#28 同哲学）。

---

## 5. 交接（handoff）

### 5.1 确认后的方向如何交给实现

- **stage 流不变**：decision 阶段（decision-report.md）→ preview*（可选）→ fill。Fill 消费面仍是现行顶块（scene/density/template/regions/components/baseline-changes/risks）；DD 条目是其**依据层**——Fill 或后续评审需要「为什么是这个方向」时按 id 追溯。
- **spec 投影关系**：呈现层差异 → DD 条目 + spec 段回写（G1 复验）；**实质不同结构**（超出呈现层、动摇已确认 IA/主路径）→ 不在 D3 裁决，回流成形 CP-B 类问题（#28 边界：D3 接手的是 spec 之后的探索）。
- **craft-guard / 评审消费**：检测器与 finding 遇「视觉方向与基线冲突」时按 R3 路由，finding 以附加字段行 `dd: <run>/DD-0003` 引用被挑战条目（与 #30 `rule:` 行同一向后兼容机制）。

### 5.2 provider 资产的引用方式（引用层，不做证据）

- 候选工件（草图/线框/原型文件）存 run 本地目录（如 `.scratch/<run>/candidates/`），DD 条目内以 `path + sha256` 引用——**引用层，不入 manifest 证据层**（决议 Q5，2026-08-14）。
- 理由：manifest 是 criterion↔artifact 的证据接缝（D5 语义），设计探索发生在实现之前，没有 L6 运行时证据可绑；provider 工件只服务人的比较，**不是证据**（Provider 边界：产出 artifacts、永不产出 evidence）。preview 的 round HTML 已有自己的哈希接缝（事务 binding）。
- **可替换性**：资产随 run 归档可弃；协议绑定的只有决定与理由，不绑资产格式——换 provider 不影响任何 DD 条目的有效性，丢资产只损失复盘素材，不损失决定 provenance。

---

## 6. 重入（re-enter）

### 6.1 R3 回流到设计决策的语义

- **定位**：finding（R3 触发特征：方案假设失败 / 取舍未记录 / 视觉方向与基线冲突）以 `dd:` 行指名被挑战条目与失败点（哪条假设、哪个 trade-off 失效）。
- **失效范围（最小集）**：该 DD 条目（`status: invalidated`）+ 消费该方向的 Fill 实现面 + 依赖其假设的 L6 证据（进 #29 `invalidated:` 失效证据集）；未受影响条目与证据保留。
- **修订语义**：**新 DD 条目 `supersedes` 旧条目**（append-only，不改写历史——与 decisions.jsonl / #30 版本化同构；决议 Q7，2026-08-14）；旧条目保留可解析。每次重开**不是**新 run：run 内闭环，重评只跑失效集 + 相邻主路径（D6 最小修复）。
- **重新定档与确认**：修订后的方向按 1.2 重新判档——仍是方向级 → 用户再确认（preview 在场走新一轮 round，`round_n` 递增，G5 校验新 confirm）；基线内替代 → 代理自主。基线冲突类 R3 的修订只有两条合法出路：改选遵循基线的候选，或走 `baseline-changes` 显式批准——不允许静默改基线。

### 6.2 基线漂移时既有决定的复核（三出口规则，2026-08-14 用户确认）

- 触发：`design_baseline.verify` 检出来源哈希漂移（既有重验机制）→ 引用旧 sha 的 DD 条目标 `stale`。
- 复核 = 在新基线下重跑该条目的约束比较（选择是否仍成立），结论三选一：**保持**（记录复核行 + 引用新 sha，解除 stale）/ **修订**（supersedes 新条目，按档位重新确认）/ **升级呈报**（漂移使问题回到方向级）。
- 复核记录并入 design-baseline 既有「发现/确认/重验」记录面（#24 D3 输出定义）；无日历 TTL，过期仅由结构事件触发（CONTEXT「Avoid calendar-only expiry」）。

---

## 7. 走查示例：「数据导出入口」（沿用 #28/#29 同一例子）

背景：#28 S6 已通过——D-0001…D-0006 已确认（`l1.*`、`l6.c1/c2`、`l2.entry_choice`=B 行内批量导出）；`export.row_cap` 等 4 个 assumed 已 ack；spec L1-L6 齐全。现进入 decision 阶段（ui-picker），日期 2026-08-14。

**幕一 R 档直录（基线内小选择，对齐耗时关切）**：导出触发控件形态。组件角色表判定「批量主行动」→ Button（icon+label）；密度跟随基线 console-tight 段。单一合理选择 → R 档，不比较、不问用户：

```yaml
id: DD-0001
tier: record
question: 导出触发控件形态
status: confirmed-agent
selection: {candidate: Button(icon+label), rationale: 组件角色表「批量主行动」+ 基线密度段直接决定}
constraints: {baseline: DESIGN.md sha256:<digest>, spec: [l4.export-trigger]}
```

顶块 `components:` 同步落值。耗时：一次字段填写。

**幕二 C 档轻量比较（基线内多案，代理自主 + 记录取舍）**：导出文件命名。两案：A `export-<时间范围>.csv` vs B `export-<固定名>-<时间戳>.csv`。轴（任务适配：运营周报归档检索——`l1.target_user`）：A 按周归档可读性高；B 万能但检索需重命名。trade-off 一行，代理选 A：

```yaml
id: DD-0002
tier: compare
question: 导出文件命名模式
status: confirmed-agent
candidates: [{id: A, source: agent, summary: 时间范围命名}, {id: B, source: agent, summary: 固定名+时间戳}]
comparison: {axes: [{axis: 周报归档检索, from: l1.target_user, A: 支持, B: 不利}],
             tradeoffs: "A 以命名约束换归档可读；B 以通用性换检索成本"}
selection: {candidate: A, rationale: 周频归档场景检索是主任务, rejected: [{candidate: B, reason: 周报场景需二次重命名}]}
confirmation: {kind: agent, via: agent-record, confirmed_at: 2026-08-14T10:20:00Z}
```

不问用户（Q7 第 4 行）；比较与取舍已留档，后续 R3 有锚可指。

**幕三 E 档完整探索（两案比较 → 用户确认 → 记录 → 交接）**：起草 region 分配时浮出——行内批量导出进行中（可达 30s），状态呈现需要构成级方案。候选 A：行内进度条嵌入各选中行 + 工具列总进度（强化 action region）；候选 B：启用全局 status region 收纳导出任务，主列表仅禁用 + 行内微标（新增 region 权重）。**命中判据 2（region 集合/权重重组 = 构成变化）**→ E 档。候选 B 由 provider 适配器渲染草图（`candidates/B.html` + sha256，deviations 空）。

比较矩阵（节选）：

| 轴（来源） | A 行内进度 | B 全局状态区 |
| 任务适配·导出中切页（`l1.scenes`） | 不利：切页后状态无处可查 | 支持：全局一处可查 |
| 感知反馈相称性（PERF-01@1，advisory） | 部分：短导出足够 | 支持：长导出有持续进度感 |
| 基线·布局段（DESIGN.md） | 遵循（不新增 region） | 遵循（启用既有 status region 惯例） |

trade-offs：「A 以上下文邻近换操作区占用与切页丢失；B 以全局可见换离上下文远。」硬约束规则无命中（无排除）。

用户确认（preview 在场）：`run_preview_transaction(summary="导出进行中的状态呈现构成", round_n=1, report_ref="decision-report.md", options=["A 行内进度", "B 全局状态区"], …)` → 用户选 B，feedback 通过 floor → `confirm-round-1.json`（confirmed=true, selected_options=["B 全局状态区"], decision_id `<uuid>`）→ G5 过。

记录：DD-0003 即 4.1 示例全文（tier: explore，candidates 含 B 的 provider-adapter provenance 与资产哈希，selection.rationale 回指「切页场景 + 长导出反馈」两轴，rejected A 理由完整）。用户未声明项目约定 → 不投影决定日志；不涉 token → `baseline-changes: none`。

交接：spec L2 回写「status region：收纳进行中导出任务」职责行 → G1 复验过；顶块 `regions:` 增 status 区；Fill 消费顶块实现。（此后进入 #29 的评审幕，此处不重复。）

**幕四 R3 挑战 → 重入修订**：评审交互轨 finding：「切页返回后全局状态区清空，导出结果不可获知」（跨视图状态闭环维度，S2 事实类，interaction 轨迹证据）。R3 路由：`source: design` + `dd: DD-0003`——被挑战的是 B 案假设「状态区条目跨页保持」。

失效集：DD-0003（status: invalidated）+ Fill 的 status region 实现 + 依赖该假设的 c1 相邻证据行（入 `invalidated:` 块）。修订：新条目 **DD-0004 `supersedes: DD-0003`**——B′ = 全局状态区 + 任务条目持久化（返回列表页时恢复显示，含完成态入口），仍命中构成判据 → E 档 → 用户再确认（round_n=2 新事务，G5 校验新 confirm）；spec L2/L5 回写（状态区职责 + 返回保持行）；重评只跑失效集 + 主路径相邻节点。DD-0003 保留可解析，历史不改写。

**幕五 基线漂移复核**：后续 run 中 DESIGN.md 声明的来源文件重构 → `verify` 检出漂移 → 引用旧 sha 的 DD-0003/0004 标 stale → 复核：新基线布局段未改变 region 惯例 → 记复核行「保持 + 新 sha256 引用」，stale 解除。全程无日历 TTL。

---

## 8. 对后续工单的接口

| 工单 | 本原型交出的接口 |
| --- | --- |
| #32 | DD 条目块正式 schema 与机器可查面落码（G 编号届时编排）；`<run>/DD-<n>` 跨 run 引用解析；stale 复核状态；finding `dd:` 附加字段行进正式 schema；D3 侧分层执行轮廓与三档触发的 run profile 合并 |
| #33 | 首切片最小集建议：R/C 档全量 + E 档协议（含 preview 搭乘与缺席路径）；顶块与 stage registry 零改动 |
| #29（已定稿，回执） | R3 finding 特征 → `dd:` 行引用约定即本文 5.1/6.1；失效证据集消费 DD 条目粒度 |
| #30（已定稿，回执） | 规则参与比较 = 只读轴/过滤器（2.1），引用钉 ID@version 交叉 G8；不要求 executes-in 枚举变更 |

---

## 已确认决议（2026-08-14，用户裁决：全部按建议采纳）

| 题 | 问题 | 决议 |
| --- | --- | --- |
| Q1 | 探索触发分档 | **A：三档 R/C/E**——直录（R，单一合理选择，一句理由）、轻量比较（C，基线内 2-3 案，代理比较 + 记录取舍，不问用户）、完整探索（E，识别度/构成级，用户确认）；C 档是现行「2-3 IA 变体分支」的正式化，只加深记录义务，不改变 Q7 决策权；基线内小选择永不触发完整探索 |
| Q2 | 设计决定条目的记录载体 | **A：深化 decision-report.md 为版本化 markdown 结构块**——顶块（Fill 消费面）逐字保留，DD 条目块追加其后（与 #30 rules.md 同一可校验风格）；不新增文件，stage registry 零改动 |
| Q3 | 方向级决定的持久化路径 | **A：双轨**——持久视觉方向走 design-baseline 显式批准（DESIGN.md 原子写）；持久行为/结构意图走 decisions.jsonl 投影（`<domain>.*` 词表，仅用户显式声明项目约定时）；默认 run-scoped 留在 DD 条目 |
| Q4 | provider 接口的抽象层级 | **A：数据契约级**——只定义候选描述符的输入/输出形状，不定义工具名、调用面、传输；任何来源（代理/适配器/用户带入）产出该形状即合法 |
| Q5 | provider 资产的引用方式 | **A：引用层**——DD 条目内 `path + sha256` 引用，资产存 run 本地目录，不入 manifest、不作证据、随 run 可弃；换 provider 或丢资产不影响决定有效性 |
| Q6 | 用户确认的通道 | **A：preview 在场时搭乘事务，缺席时走报告确认记录**——在场：options=候选、report_ref=报告、G5 校验、条目链接事务 decision_id；缺席：confirmation 块直接落 DD 条目（+ 需持久时投影决定日志）；协议不因适配器缺席而降级 |
| Q7 | R3 重入的修订语义 | **A：supersedes 新条目 + 最小失效集 + 按新档位重新确认**——旧条目标 invalidated 保留可解析；失效范围 = 条目 + 消费它的实现面 + 依赖其假设的证据（进 #29 invalidated 集）；run 内闭环重评最小集；与 decisions.jsonl、#30 规则版本化、#28 证伪重开子树同构 |

基线漂移复核三出口规则（stale 标记 + 保持 / 修订 / 升级呈报、无日历 TTL，6.2 节）同日经用户确认，无异议。
