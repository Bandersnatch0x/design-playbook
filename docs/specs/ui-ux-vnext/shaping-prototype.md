# 交互式需求成形决策模型原型（Interactive requirement shaping — decision model prototype）

- 工单：#28（wayfinder:prototype）。域：D1 需求成形 RS（Interactive requirement shaping）。
- 状态：**已定稿**。2026-08-14 用户裁决：6 项待决问题全部按建议采纳（Q1-Q6，见文末「已确认决议」）。
- 性质：纸面决策模型定稿（规划型地图产物）。不实现产品代码、不改技能与脚本；本文交付的是**决策模型、迁移规则与工件投影图**，供 #32 落 schema 与状态机。
- 上游锁定决议（不可推翻，只细化）：#24 矩阵定稿的 8 域划分、Q3=A（会话工件为第一方持久运行工件，确认后**投影**到契约与 spec；契约是唯一持久决定权威，会话是成形过程权威；生命周期留本工单）、Q7=A（按后果分级的决策权默认表）。
- 本原型回答工单五问：决策树、三态与 open 处理、人工确认点、中断/恢复与生命周期、工件关系（无第三 SSOT）。

## 0. 真实 schema 基础（投影的落点，全部来自已交付代码）

投影规则只落到已存在的字段名与函数，不发明新 schema：

- **contract.json（持久契约 v1，`packages/design-playbook/scripts/contract_v1.py`）**：`schemaVersion: 1`；`fields[path] = { value, provenance: observed|inferred, resolution: decided|assumed|open, source_hash?, notes? }`；`changelog: [{at, summary}]`。字段路径是任意非空字符串——v1 **没有路径词表**，`l1.*` / `l6.cN` 等命名是本模型确认采用的词表（决议 Q6，2026-08-14；保留条件：若 #32 发生更大 schema 重构则重估词表），不是 schema 发明。`value` 无类型约束（可承载结构化 JSON）。
- **decisions.jsonl（决定日志，append-only）**：每行 `{ id, field, decision, rationale, confirmed_at, supersedes? }`；id 匹配 `^[A-Za-z0-9][A-Za-z0-9_.-]*$`；`supersedes` 必须指向已存在 id，修订永不改写历史。
- **权威机制**：`promote_fields` **拒绝制造 `decided`**（只收 assumed/open）；`decided` 只能由 `append_decision`（用户显式确认后）+ `apply_decisions` 产生。`bind_first`：`open` 字段恒阻断；`assumed` 字段须逐 run 显式确认（acknowledgement）才放行；`source_hash` 漂移须复核；产出 `contract-bind.json` 快照。
- **spec.md（ux-spec 六层，`packages/design-playbook/skills/ux-spec/`）**：L1 定位与意图（用户可见目标 / 目标用户 / 场景清单 / 非目标 / 行为边界：始终/询问后/永不）、L2 信息架构、L3 核心链路、L4 组件功能细节、L5 边界条件（空/加载/错误/权限）、L6 验收标准（顶层列表项，`Given → When → Then` 顺序固定 + 必备证据 + capture seed，3-7 条软预算）。G1 校验 L1-L6 标题齐全。技能 step 0 已要求 bind-first；step 1 已要求假设显式标注。
- **G7（契约漂移门禁）**：契约 ↔ 决定日志 ↔ 归一化字段的哈希一致性，未记录漂移产生机器可读失败。
- **run 记录**：`.scratch/<run>/` 单 run 工件目录（spec / plan / decision / evidence / point-back / contract-bind.json）。run 契约五控制：Goal、Success、Evidence、Stop、Confirm。

---

## 1. 决策树：从模糊请求到确认意图 + run 范围 UX spec

### 1.1 主线状态机

```
S0 INTAKE 受理
 │  谁触发：用户（提出模糊 UI 请求）
 │  动作：逐字记录请求原文；装配输入——持久契约 + 决定日志（bind 语义预检）、
 │        项目设计基线（DESIGN.md / design-baseline state）、既有 spec、
 │        参考契约（reference-intake 产物，功能约束折入 L1 的既有规则）
 │  迁移：→ S1（自动，无门禁）
 ▼
S1 GRADE 后果分级（consequence grading）
 │  谁触发：代理
 │  动作：按 Q7 表对四个面做缺口/歧义/矛盾分级——
 │        T1 consequential（产品目标/目标用户/成功判据/非目标）
 │        T2 structural（实质不同的 IA / 主路径替代）
 │        T3 visual-identity（改变识别度/构成的视觉方向——成形期只登记路由给 D3，不裁决）
 │        T4 local（已确认声明内的局部实现——代理自主，永不提问）
 │        产出：问题队列（question queue，按 T1>T2>T3 排序）+ 假设预案（assumption plan）
 │  迁移：存在 T1 待问项或待确认的 T1 假设 → S2；
 │        全部字段已有契约值且无新缺口（重复 run 常见）→ 直接 S3
 ▼
S2 CLARIFY 澄清提问
 │  谁触发：代理呈批（≤3 问/批），用户作答
 │  动作：每问必须绑定「答错会改变哪个下游字段 / 哪条 L6」；T1 未清不问 T3；
 │        连续 2 批无新 T1 信息 → 剩余 T2/T3 项必须转入假设预案而非继续追问（问题疲劳上限）
 │  迁移：T1 队列清空（余项走显式风险确认）→ S3；单问拒绝作答 → 该项降级为
 │        「T1 显式风险假设」进 CP-C（代理不得静默 assumed，见 1.3）
 ▼
S3 DRAFT 起草
 │  谁触发：代理
 │  动作：以确认值 + 已登记假设起草 spec L1-L6；起草中浮出实质不同的 IA / 主路径
 │        替代 → 生成 T2 结构问题回 S2（每轮起草最多回跳 1 次）；T4 局部选择直接落稿
 │  迁移：草稿覆盖 L1 五字段 + L6 判据 → S4
 ▼
S4 CONFIRM 批量确认（人工确认点，见第 3 节）
 │  谁触发：代理呈批，用户逐项裁决（确认 / 拒绝 / 改写）
 │  迁移：全部批次处理完 → S5；单项拒绝/改写 → 仅该项回 S2 重生成（已确认项不受牵连）
 ▼
S5 PROJECT 投影
 │  谁触发：代理执行，门禁校验
 │  动作（严格按既有函数序）：promote_fields（登 assumed 字段）→ 逐条 append_decision
 │        （用户已确认项）→ apply_decisions（落 decided）→ 写 spec.md → bind_first
 │        （生成 contract-bind.json + assumed ack 清单）→ G7 漂移校验
 │  迁移：G7 干净 → S6；漂移 → 阻断，回 S1 以新契约重分级
 ▼
S6 EXIT 成形结束判据（门禁，全部满足才放行）
     a. 绑定子集内 open 字段数 = 0（bind_first 语义：open 恒阻断）
     b. 所有 assumed 字段已获本轮显式 ack（CP-E）
     c. L1 五字段 + L6 判据全部有值且来源可追溯（decided 或 acknowledged-assumed）
     d. decisions.jsonl 与 contract 无未记录漂移（G7）
     e. spec.md 六层标题齐全（G1）
     输出：确认的产品意图（契约字段 + 决定日志条目）+ run 范围 UX spec + 开放问题队列余项；
     会话归档（见第 4 节）；交棒 D2 深化（L2-L5 结构化）与 ui-picker
```

任意状态可 `suspended`（中断）；恢复规则见第 4 节。成形失败没有「静默降级」出口：要么 S6 通过，要么以显式未完成状态挂起（open 队列与理由随会话保存）。

### 1.2 澄清问题如何生成与排序

生成来源（S1 扫描）：

1. L1 五字段覆盖分析（目标/用户/场景/非目标/边界——缺项即候选问题）；
2. 成功判据缺口（无 L6 种子可写 = 判据缺口）；
3. 请求原文与项目契约 / 设计基线 / 既有 spec 的**矛盾检测**（矛盾优先级高于缺项）；
4. 参考契约（reference-intake）的 Do-not-copy 隐含非目标。

排序键（字典序）：`(tier 升序, 下游依赖数降序, 与已给线索的冲突度降序)`。每问携带影响注记——例：「本问决定 `l1.goal` 与全部 L6 条目的表述」；无下游影响的问题不配问（转 T4 假设）。

### 1.3 何时允许假设而非提问（防问题疲劳）

| 层 | 允许的处置 |
| --- | --- |
| T1 consequential | **禁止静默假设**。要么提问（S2），要么以「显式风险确认假设」进 CP-C 由用户点头（风险与回退值一并呈报）。依据：Q7 第一行 + `promote_fields` 的代码级禁令 |
| T2 structural | 实质不同时必须问（CP-B）；「同基线内的位置/顺序微差」可保守假设并在 CP-C 列出 |
| T3 visual-identity | 成形不裁决：登记路由条目（open question → D3），不阻塞成形结束，除非它使 L1 边界含糊（此时升为 T1） |
| T4 local | 永不提问，直接保守假设（assumed）或落稿，CP-C 汇总可见 |

批次上限与疲劳策略：每批问题 ≤3；连续 2 批无新 T1 信息后禁止继续追问 T2/T3（强制转假设预案）；整个会话问题总数软上限 9（3 批 × 3 问），超出需用户显式同意继续。

---

## 2. 假设与 open 态处理（decided / assumed / open）

### 2.1 三态迁移规则（唯一合法路径）

| 从 | 到 | 触发者 | 机制与记录位置 |
| --- | --- | --- | --- |
| open | assumed | 代理（仅 T2-T4 保守缺省）；或用户（T1 显式风险接受，回退值一并写入） | `promote_fields` 落 `resolution: assumed` + `notes`（理由/风险/回退）；会话假设批次留档 |
| open | decided | 仅用户显式确认 | `append_decision` + `apply_decisions` |
| assumed | decided | 仅用户显式确认；修订走 `supersedes` 新 id | `decisions.jsonl`（append-only，不改史） |
| assumed | open | 假设被证伪或来源漂移，当前值不可再用 | 契约字段回 open + 新会话重开失效子树 |
| decided | assumed / open | 证伪或用户主动修订（`supersedes`） | `decisions.jsonl` 新条目 + G7 漂移复核 |

代理自升 `decided` 在代码层已被 `promote_fields` 拒绝——本模型不新增任何绕过通道。

### 2.2 老化与升级（aging & escalation）

- 逐 run 再确认：既有 `bind_first` 语义原样保留——每个 run 绑定契约时，全部 `assumed` 字段浮出并要求本轮 ack（CP-E）。
- 升级规则（决议 Q1 确认）：同一 `assumed` 字段在**连续 2 个 run 被 ack** 仍未转 `decided` → 下次成形会话自动升为 T1 必答问题（不再接受「继续 ack」）。计数**从历史 run 记录（contract-bind.json 快照与归档会话）派生**，不新增持久状态（与 run aggregate 读 `.scratch/**/` 历史的既有模式一致）。
- `open` 不老化：open 只有两条出路——被决定（decided），或被用户接受风险后降级为带回退值的 assumed。open 不存在「放着变安全」的通道。

### 2.3 open 何时阻塞成形结束

S6 判据 a：绑定子集内 open 字段数必须为 0。这与 `bind_first` 的「open 恒阻断」完全同构——成形结束面与 run 绑定面用同一条规则，不产生第二套阻断语义。用户对 open 的唯一处置是 CP-D：解决（转 decided）/ 接受风险（降级 assumed + notes 记录回退值与接受时间）/ 显式中止成形。

### 2.4 假设被证伪时的回滚范围（falsification & rollback）

触发：run 内评审（D4/D5）证据、后续 run 观察、或用户陈述与某 `assumed` 字段矛盾。

失效集计算（最小集，对齐 D6 point-back 哲学）：

1. 被证伪的契约字段本身；
2. 契约中以该字段为派生来源的字段（投影时在 `notes` 登记来源链）；
3. spec 中由上述字段派生的 L1 子项、L2-L5 段、L6 条目；
4. 绑定在这些 L6 上的证据行（进 D6 失效证据集）。

回滚动作：失效字段回 open；涉及的决定用 `supersedes` 修订（决定日志不删史）；**新开成形会话只处理失效子树**（supersedes 旧会话，见 4.3），不复盘整个需求。跨子树不受影响——这是「最小修复」在成形侧的对应物。

### 2.5 assumed 在 spec / verdict 中的可见性义务

- **spec**：L1 每个假设值显式标注「假设」并指向契约字段路径（ux-spec step 1 的 done-when 已要求 assumption labeled as such——本模型把它从风格约定升为投影义务）；由假设派生的 L6 条目在必备证据处标注依赖假设。
- **run 契约 Confirm 控制**：列出全部 assumed ack 项（CP-E 清单即其内容来源）。
- **verdict / point-back**：评审发现涉及 assumed 字段时必须引用其假设状态；没有对应契约声明的发现回流 D1（重开成形），不在评审中现场发明产品要求（#24 D4 既定边界）。
- **老化计数与升级历史**：随归档会话可见（审计用），不进 spec 正文。

---

## 3. 人工确认点（Q7 默认表 → 成形流程的具体检查点）

| 检查点 | 对应 Q7 行 | 时机 | 粒度上限 | 语义 |
| --- | --- | --- | --- | --- |
| **CP-A 产品意图批次** | 第 1 行（产品目标/目标用户/成功判据/非目标 → 用户确认） | S4，一次 | ≤4 项（每字段一项） | 逐项：确认 / 拒绝 / 改写；每项附「它驱动哪些 L6」 |
| **CP-B 结构性批次** | 第 2 行（实质不同 IA / 主路径替代 → 用户确认） | S3 浮出时 | ≤2 项，每项 ≤3 案 | 选项 + 每案验收范围差异注记；选定后写入 l2.* 字段 |
| **CP-C 假设确认批次** | 第 1 行的 T1 显式风险假设 + T2-T4 保守假设汇总 | S4 | ≤5 项 | 每项：理由 + 风险 + 回退值；确认 / 拒绝（该项回 S2）/ 改写（改值后重登） |
| **CP-D 遗留 open 处置** | 第 5 行（blocking 处置：改变声明或接受风险时用户介入） | S6 前 | 逐项 | 解决（转 decided）/ 接受风险（降级 assumed）/ 中止 |
| **CP-E run 级假设 ack** | bind-first 既有语义（assumed 每 run 再确认） | 每次 bind（含成形产出的 run） | 全部 assumed 字段 | 沿用 acknowledgements 机制，不新造 |
| T3 视觉方向路由 | 第 3 行（改变识别度/构成的视觉方向 → 用户确认） | 登记即走 | — | 成形只登记 open question 路由给 D3 决策报告（#31），不在成形内确认 |

拒绝/部分拒绝语义（全检查点统一）：

- **批次内逐项原子**：同批已确认项不因他项被拒而回退；部分确认合法。
- **拒绝**：该项携拒绝理由重入 S2 问题队列（只重生成该项，不重放整批）。
- **改写**：等价于拒绝 + 用户给定新值候选，新值走同一确认路径。
- **已确认项不可变**：修订只能通过 `supersedes` 新决定条目（append-only 哲学贯穿到确认层）。

---

## 4. 中断/恢复与会话工件生命周期（Q3 留给本工单的决策）

### 4.1 会话工件（第一方持久运行工件，过程权威）

```
.scratch/<run>/shaping/
  shaping-log.jsonl   # append-only 事件日志（过程权威，镜像决定日志哲学）
  queue.json          # 派生态：待答队列 / 假设批次 / 确认批次（可随时从 log 重建）
```

事件类型（枚举供 #32 定稿）：`asked / answered / assumption_staged / confirm_presented / item_confirmed / item_rejected / item_revised / projected / suspended / resumed / superseded_by / archived`。

快照内容：请求原文（逐字）、每问的影响注记、每假设的理由/风险/回退、每确认项的状态与时间戳、S1 分级结果、投影执行记录（决定 id ↔ 契约字段 ↔ spec 段的映射）。

### 4.2 任意时刻中断后恢复

- **中断**：任意状态写入 `suspended` 事件即可；无额外持久化要求（log 本身就是快照序列）。
- **恢复重放**：从 `shaping-log.jsonl` 重建 `queue.json`；只重发「asked 未 answered」的问题；已 `item_confirmed` 且已落 `decisions.jsonl` 的项**绝不重问**（confirmed_at 即免重问凭证）。
- **中断期间契约漂移**：恢复时先重跑 `bind_first`；契约 SHA 变化则 diff 受影响字段——受影响的未确认项作废重开，不受影响的确认项保留（决定日志 append-only 保证不丢）。
- **过期**：**无日历 TTL**（CONTEXT.md 术语表明确 Avoid「calendar-only expiry」）。过期仅由结构事件触发：(a) 同范围新会话开启（旧的写 `superseded_by` 后归档）；(b) 契约/schema 漂移使 staging 基础失效且用户不在本会话和解。

### 4.3 生命周期三阶段（决议 Q2 确认，2026-08-14）

| 阶段 | 区间 | 可写性 | 退出条件 |
| --- | --- | --- | --- |
| **alive 存活** | S0 受理 → S5 投影通过 G7 | 可写（事件追加） | S6 判据满足 |
| **archived 归档** | S6 通过 → run 最终 verdict | 只读（run 记录内的过程证据） | run 到达最终 verdict（Pass / Recirculate 关闭）且无未决 point-back 引用该会话 |
| **discardable 可弃** | verdict 后 | 可清理 | 显式清理动作（随 run 记录归档节奏） |

- 归档期保留的理由：证伪回滚（2.4）与审计都高频发生在 run 进行中——这正是归档窗口；verdict 后失效风险急剧下降。
- **可弃之后的持久权威只剩**：contract.json + decisions.jsonl（决定权威）+ run 记录中的 spec（呈现）。会话弃后不可复活：重开成形 = 新会话，`superseded_by` 指向旧会话 id（若旧会话已弃则指向其归档摘要行）。
- 依据：Q3=A 的定位是「会话是成形**过程**权威」——过程证据的可弃终点应绑定它服务的 run 的终点，而不是日历或次数。

---

## 5. 工件关系与字段级投影图（无第三 SSOT 论证）

### 5.1 投影图（会话条目 → 契约 → 决定日志 → spec → run 契约）

| 会话条目（事实出生地） | contract.json `fields[...]` | decisions.jsonl | spec.md | run 契约五控制 |
| --- | --- | --- | --- | --- |
| 产品目标确认项 | `l1.goal` = decided | `{id, field:"l1.goal", decision:<目标文本>, rationale, confirmed_at}` | L1 用户可见目标 | Goal |
| 目标用户确认项 | `l1.target_user` = decided | 同上模式 | L1 目标用户 | — |
| 场景确认项 | `l1.scenes` = decided | 同上 | L1 场景清单 | — |
| 非目标确认项 | `l1.non_goals` = decided | 同上 | L1 非目标 | Stop（非目标部分） |
| 行为边界确认项 | `l1.boundaries` = decided | 同上 | L1 行为边界（始终/询问后/永不） | Stop |
| 成功判据第 n 条 | `l6.c1…cN` = decided（value 为 Given/When/Then 结构化文本 + 证据类型 + capture seed） | 同上 | L6 顶层列表项 + 必备证据 + capture seed | Success、Evidence |
| T2-T4 保守假设 | 对应字段 = assumed + `notes`{理由, 风险, 回退, 派生来源链} | **不写**（假设不是决定） | L1/L6 处标注「假设」+ 字段路径 | Confirm（ack 清单） |
| T1 显式风险假设 | = assumed + `notes`「用户于 <时间> 接受风险，回退=X」 | **不写 decided**（风险接受不是值决定，写日志会错误制造 decided） | L1 假设标注 | Confirm |
| 结构性选择 | `l2.*`（如 `l2.entry_choice`）= decided | 同上（rationale 含各案取舍） | L2/L3 相应段 | — |
| 遗留 open | **不进入 run**：要么 CP-D 解决，要么降级 assumed | — | 不出现（open 值禁止写入 spec） | — |

run 契约五控制的派生关系：Goal ← `l1.goal`；Success ← `l6.c1…cN`；Evidence ← 每条判据的必备证据/capture seed；Stop ← `l1.non_goals` + `l1.boundaries` + D6 轮次预算；Confirm ← CP 批次清单 + assumed ack 清单。

**契约 v1 schema 扩展重估结论（#24 明确留给本工单的问题之一）**：本模型**不需要破坏性 schema 扩展**——字段路径本就是自由字符串；`value` 无类型约束（可承载 Given/When/Then 结构）；`notes` 足以承载假设理由/风险/回退/来源链。新增的是**文件**（shaping-log.jsonl / queue.json），不是契约 schema 变更。路径词表已按决议 Q6 确认（层号 + 概念域前缀）；留给 #32 的是事件枚举正式化与词表并入 schema 定稿——**若 #32 发生更大的 schema 重构，词表届时重估**（Q6 保留条件）。

### 5.2 为什么不产生第三 SSOT

每类事实同一时刻只有一个可写权威，且无绕行通道：

| 事实类型 | 唯一可写权威 | 说明 |
| --- | --- | --- |
| 值的出生（问题/假设/确认条目） | 会话工件 | 归档后只读；重开 = 新会话 |
| 值的持久 | contract.json | 唯一写入口是 `promote_fields` / `apply_decisions`（既有函数） |
| 确认史 | decisions.jsonl | append-only；`decided` 只能经用户确认产生 |
| 呈现 | spec.md | 契约 + run 范围的**投影视图**，不作为意图编辑面（与 Capture Plan「派生、不为意图而编辑」同哲学） |

交叉校验全部落在既有机械面：G7（契约 ↔ 决定日志漂移）、bind_first（assumed/open 再浮出 + ack）、G1（spec 六层结构）。会话不提供任何「绕过契约写入决定」的路径——`promote_fields` 的 decided 禁令是代码级保证，因此会话是过程权威而非第二个决定权威。

### 5.3 与 ux-spec L1-L6 的衔接

- 成形会话 = ux-spec 技能 step 1 的**有状态化改造**（「缺失答案实质改变 L1 五字段才问，否则记保守假设」的既有规则，从代理即兴行为升级为状态机 + 批次 + 门禁），并把 step 0 bind-first 前置为 S0 输入装配。
- L1 五字段与 `l1.*` 契约字段一一对应（同名路径即投影映射，可机械校验）；L6 判据与 `l6.cN` 一一对应，3-7 条软预算与 capture seed 规则原样沿用。
- L2-L5：成形内代理起草（T2 结构问题经 CP-B 确认，T4 局部选择自主）；结构化字段深化（逐页职责、五态、路径）归 D2/#32——成形不阻塞该深化，只保证它启动时 L1/L6 权威已定。

---

## 6. 走查示例：「给控制台加一个数据导出入口」

中性模糊请求，完整走一遍模型（日期用 2026-08-14）。

**S0 受理**：原文逐字入档：「给控制台加一个数据导出入口」。输入装配：项目契约存在（仅基线字段，无导出相关决定）；无参考契约；设计基线在位。

**S1 分级**：

| 缺口 | 层 | 处置 |
| --- | --- | --- |
| 产品目标（导出为谁解决什么） | T1 | 入问题队列 Q1 |
| 目标用户（谁在导出、频率） | T1 | Q1 合并问 |
| 成功判据（导出「完成」的定义） | T1 | Q2 |
| 非目标（调度/全量历史是否明确不做） | T1 | Q3 |
| 导出规模上限 | T1（影响判据） | 队列满 → 假设预案（显式风险确认） |
| 入口位置（全局工具栏 vs 行内） | T2 | 留待 S3 起草浮出 |
| 文件命名、进度提示形态 | T4 | 代理自主，不问 |

首批问题（≤3，T1 优先，按下游依赖排序）：

- Q1「这次导出要帮谁完成什么任务？」（影响 `l1.goal`、`l1.target_user`、全部 L6）
- Q2「导出『完成』对用户意味着什么——拿到文件即算，还是含列选择/时间范围？」（影响 `l6.c1-c3`）
- Q3「定时/周期导出、全量历史导出，是否明确不做？」（影响 `l1.non_goals`、`l1.boundaries`）

**S2 澄清**：用户答：「运营同学每周导上周数据做周报，CSV 就行，别做定时任务。」→ 拟定 `l1.goal`（支持运营完成周报所需的数据导出）、`l1.target_user`（运营角色，周频）、`l1.non_goals` 线索（不做调度）。规模上限未答 → 转 CP-C 显式风险假设。T1 队列清空 → S3。

**S3 起草**：L1/L6 草稿成型；浮出 T2：入口 IA 两案——A 全局工具栏「导出」按钮（影响全部列表页）/ B 主列表行内批量导出（范围收敛）。实质不同 → CP-B。L6 草稿：`l6.c1`（选定范围 → 行内批量导出 → 限时内获得 CSV 且行数与选中一致，证据=交互记录）；`l6.c2`（超上限 → 确认导出 → 提示剩余量与收窄建议，证据=错误态截图 capture seed）。

**S4 确认批次**：

| 批次 | 项 | 裁决 |
| --- | --- | --- |
| CP-A（4 项） | goal / target_user / success（c1-c2 表述）/ non_goals（不做调度、不做全量历史） | 全部确认 |
| CP-B（1 项 2 案） | 入口 IA | 选 B（行内批量） |
| CP-C（3 项） | 上限 5 万行（改写：20 万）；同步导出限时完成（确认）；导出列=当前视图列含隐藏列开关（确认） | 改写 1、确认 2 |

**S5 投影**（严格按函数序）：

1. `promote_fields`（均 assumed）：`l1.scenes`（首场景=运营周报）、`export.row_cap`=200000、`export.sync_window`、`export.column_scope`，各带 `notes`{理由/风险/回退}。
2. `append_decision`（用户已确认项，示例一行）：

   ```json
   {"id":"D-0004","field":"l6.c1","decision":"Given 运营在主列表选定上周范围 When 触发行内批量导出 Then 30 秒内获得 CSV 且行数与选中范围一致（证据：交互记录）","rationale":"2026-08-14 用户确认的周报场景成功判据","confirmed_at":"2026-08-14T10:05:00Z"}
   ```

   另有 D-0001 goal、D-0002 target_user、D-0003 non_goals、D-0005 l6.c2、D-0006 `l2.entry_choice`=B。
3. `apply_decisions`：上述字段落 decided。
4. 写 spec.md：L1 五字段与 `l1.*` 一一对应；c1/c2 落 L6 顶层项；`export.*` 假设在 L1 标注「假设」+ 字段路径。
5. `bind_first`：4 个 assumed 全部 ack（CP-E），open=0 → `contract-bind.json`。
6. G7 无漂移 → **S6 通过**：a open=0 ✓ b assumed 已 ack ✓ c L1+L6 有值可溯 ✓ d G7 ✓ e G1 ✓。会话归档（alive → archived）。

**后续证伪一幕（回滚演示）**：run 内观察发现隐藏列含敏感字段被导出 → `export.column_scope` 假设证伪 → 失效集 = `export.column_scope` + `l6.c1`（其行数/列表述依赖该假设）+ L4 导出列细节 + 相关证据行 → 字段回 open，新会话（`superseded_by` 旧会话）只重开该子树，D-0007 `supersedes` D-0004 修订 `l6.c1`，D-0008 新增 `l1.boundaries` 永不项「隐藏列默认不导出」。子树外决定不受影响。

---

## 7. 对后续工单的接口

| 工单 | 本原型交出的接口 |
| --- | --- |
| #29 | assumed 可见性义务（评审发现引用假设状态）；证伪信号从 findings 回流 D1 的格式需求；「无对应契约的发现回流 D1」的落点即本模型的重开子树机制 |
| #30 | 问题疲劳上限、批次大小等若要机器化，按 advisory detector 入注册表（不自造阻断） |
| #31 | T3 视觉方向路由队列的条目结构（open question → D3 决策报告输入） |
| #32 | 会话工件 schema（事件枚举、queue 派生规则）、S0-S6 状态机落码、L2-L5 结构化字段、路径词表并入 schema 定稿（若大重构则按 Q6 保留条件重估）；契约 v1 零破坏性扩展的结论（5.1） |
| #33 | 成形会话是否进首切片：D1 是全部 run 的入口能力，建议随首切片交付最小集（S0/S1/S2/S4/S5 + CP-A/CP-C/CP-E） |

---

## 已确认决议（2026-08-14，用户裁决：全部按建议采纳）

| 题 | 问题 | 决议 |
| --- | --- | --- |
| Q1 | 假设老化与升级阈值 | **A**：连续 2 个 run ack 未转 decided → 下次会话强制升级为 T1 必答问题；计数从历史 run 记录派生，不新增持久状态 |
| Q2 | 会话工件生命周期终点（#24 决议 Q3 留给本工单） | **A**：alive（受理→投影验证）→ archived（S6 后冻结为 run 记录过程证据，只读）→ discardable（run 最终 verdict 且无未决 point-back 引用后可清理）；无日历 TTL；弃后持久权威只剩 contract.json + decisions.jsonl + run 记录中的 spec；重开一律新会话、永不复活旧会话 |
| Q3 | 批量确认粒度上限 | **A**：CP-A 意图批次 ≤4 项、CP-C 假设批次 ≤5 项、CP-B 结构批次 ≤2 项（每项 ≤3 案）、问题每批 ≤3 问、会话问题总数软上限 9；数字可按 D8 跨 run 信号调整 |
| Q4 | open 态进入 spec 的通道 | **A**：open 值禁止写入 spec / run；用户接受风险 = 显式降级为 assumed + notes 记录回退值与接受时间；bind_first「open 恒阻断」语义不变 |
| Q5 | 成形结束面（exit 面边界） | **A**：成形覆盖 ux-spec 全程（S6 时 spec L1-L6 齐全），用户确认权威止于 L1 + L6 + 结构性选择（CP-B）；L2-L5 局部实现代理自主（Q7 第 4 行），结构化深化归 D2/#32 |
| Q6 | 契约字段路径命名约定 | **A**：层号 + 概念域前缀——`l1.goal / l1.target_user / l1.scenes / l1.non_goals / l1.boundaries / l6.c1…cN / l2.* / <domain>.*`（如 `export.row_cap`），路径即投影映射（会话→契约→spec 同名，可机械校验）；**保留条件：若 #32 发生更大 schema 重构则重估词表** |
