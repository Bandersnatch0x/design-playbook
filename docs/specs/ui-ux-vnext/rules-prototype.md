# 第一方 UX 规则注册表与治理原型（First-party UX rule registry & governance — decision model prototype）

- 工单：#30（wayfinder:grilling）。域：D7 规则治理 RG（First-party rule registry & governance），含 D8 跨运行学习 LR（Cross-run learning）的候选队列与晋升协议接口。
- 状态：**已定稿**。2026-08-14 用户裁决：7 项待决问题全部按建议采纳（Q1-Q7，见文末「已确认决议」）。本文是纸面决策模型（规划型地图产物）：不实现产品代码、不改技能与脚本、不动 craft-guard 现有文件；注册表 schema、门禁与迁移清单的落码归 #32/#33。
- 上游锁定决议（不可推翻，只细化）：#24 矩阵 8 域与全局原则（所有权边界、证据两分、自动化默认立场、Provider 边界、按后果分级的决策权表）；#24-Q4=A（craft-guard 八检测器作为 advisory detector 迁入统一注册表，技能保留为引用/执行说明层，一并修复状态枚举矛盾，迁移细节归本工单）；#24-Q5=A（国际化/性能感知/安全体验为 advisory 占位规则，显式适用谓词，不静默跳过）；#24-Q6=B（首版仅注册表 schema + 候选队列 + 晋升标准定义，晋升闭环执行延后）；#24-Q7=A（规则晋升 → 用户裁决）；#24-Q8=A + #29 全部决议（severity 分轴 S3/S2/S1/S0、判断类 S3 永不 blocking、升级通道三选一、适用谓词三态求值、四层证据、R1-R5 回流路由、六块报告结构）；#28（老化计数从历史 run 记录派生，不新增持久状态；无日历 TTL）。
- 外部参考非权威（map.md / CONTEXT.md 已决）：外部参考样本与本地学习资料只用于检查能力遗漏；注册表 provenance 必须能区分第一方原创 / 从发现晋升 / 占位；外部来源不拥有规则解释权，正文不出现外部来源名称与第三方规则原文。

## 0. 真实 schema 基础（注册表的落点，全部来自已交付代码）

注册表只承接已存在的字段名与文件名，不发明平行体系：

- **craft-guard 检测器协议**（`packages/design-playbook/skills/craft-guard/references/detectors.md`）：八条稳定 ID `CRAFT-01`…`CRAFT-08`，每条六字段块 `**Purpose:** / **Rendered signals:** / **Source signals:** / **Legitimate exceptions:** / **Owner hint:** / **Positive fix:**`；审计行格式 `| ID | Status | Rendered evidence | Source evidence | Exception check | Positive fix |`。
- **状态枚举矛盾（本工单修复对象，横跨四个文件）**：`craft-guard/SKILL.md` 允许 `hit|clear|blocked|N/A`（N/A 须有可观察理由，空白 N/A 非法）；`detectors.md` 协议段只允许 `clear|hit|blocked`；`scripts/validate.py` 的 fixture 校验只接受三值；`ui-evaluator/SKILL.md` 消费段以「N/A rate」措辞消费检测器行。规则分散在技能、参考文档、校验脚本三处而无单一注册表，是矛盾的根因（#26 已诊断）。
- **启用面**：craft-guard 技能要求「enable detectors from the active spec/contract (or the full catalog when none is declared)」——启用子集是**契约/spec 声明**，注册表条目必须可被声明子集启用/禁用，不能假定全目录恒启用。
- **finding 四字段**（ui-evaluator SKILL.md + G2）：`issue / source / fix / severity`；severity 现值域 `high (blocking)|high|med|low`（#29-Q1 已决分轴 S3/S2/S1（+S0），旧值兼容别名与机械换算归 #32）。finding 块内附加行（如 `rule:`）被现有解析器忽略——向后兼容的规则引用通道。
- **ledger 行**：四字段 `criterion/required/observed/result`，result 值域 `{pass, fail, blocked, n/a}`；检测器行**永不进** G6 manifest 与 L6 ledger（ADR-0014 + #29 既定，迁移不改变这一点）。
- **决定日志**（`contract_v1.py`，ADR-0017）：`decisions.jsonl` append-only，行 `{id, field, decision, rationale, confirmed_at, supersedes?}`，id 匹配 `^[A-Za-z0-9][A-Za-z0-9_.-]*$`，`supersedes` 须指向已存在 id——豁免与晋升裁决记录复用同一哲学。
- **run 聚合**（`scripts/aggregate_runs.py` + `commands/run-review.md`，v0.9）：归一化 = casefold + 空白折叠后逐字符相等；repeat blocker = 同归一化 `observed` 文本跨 run 出现 ≥2（distinct runs 计数）；JSON 契约面 `{runs[], rollup, repeat_blockers[]}`；禁止叙事学习、语义聚类、自动写回。
- **门禁现状**：G1-G6 run 级（`validate_run.py` 编排 gate 模块），G7 契约漂移（条件启用）；产品级结构校验在仓库 `scripts/validate.py`（现已校验检测器六字段契约与四份 fixture）——注册表自校验的天然宿主。
- **回流两跳路由**（#29 §8）：第一跳 observable → 声明工件（`spec/domain/craft/design/components/template/native-craft/reference` + 绑定基线路径）；第二跳声明工件 → R1-R5（requirement / interaction model / design decision / implementation / evidence plan）。
- **#28 先例**：assumed 老化计数从历史 run 记录（contract-bind 快照与归档会话）派生，不新增持久状态——D8 候选计数的输入形态直接沿用。

---

## 1. 注册表条目 schema（工单项 1）

### 1.1 字段一览

机器可查字段以 ◆ 标记（枚举 / 格式 / 引用可被 G 门禁校验，见 §8）；其余为协议面字段（供执行方与裁决者阅读）。

| # | 字段 | 中文名（英） | 值域 / 格式 | 机器可查 |
| --- | --- | --- | --- | --- |
| 1 | `id` ◆ | 稳定规则 ID（stable rule ID） | `<FAMILY>-<NN>`，如 `CRAFT-01`、`I18N-01`；正则 `^[A-Z][A-Z0-9]*-[0-9]{2}$`；全注册表唯一 | 是 |
| 2 | `version` ◆ | 条目修订号（entry revision） | 正整数，从 1 起，单调递增 | 是 |
| 3 | `title` | 名称（title） | 一行短语 | 否 |
| 4 | `statement` | 规则陈述（rule statement） | 可观测量（observable）+ 用户影响（user impact）两半；「无指征不立项」禁令同样适用于规则正文 | 否 |
| 5 | `capability-domain` ◆ | 能力域（capability domain） | `D1`-`D8`（该规则保护的关切所属域；治理归属恒为 D7，不再单列字段） | 是 |
| 6 | `executes-in` ◆ | 执行面（execution surface） | `D4:product \| D4:interaction \| D4:cross-cutting \| registry-only`（registry-only = 已定义未启用，见 §2） | 是 |
| 7 | `authority` ◆ | 权威级别（authority level） | `hard-constraint \| project-declaration \| platform-convention \| measured-threshold \| advisory-aesthetic`（矩阵 D7 五级） | 是 |
| 8 | `applicability` ◆ | 适用谓词（applicability predicate） | 声明式谓词（输入：run 类型、契约字段、spec 层声明、证据面可用性）；求值三态 `applicable / not-applicable(附理由) / blocked(证据不可得)`（#29 既定，占位规则永不静默跳过） | 谓词块存在性与形状可查；求值归执行方 |
| 9 | `check` ◆ | 检查定义（check definition） | `check-type: machine-detector \| protocol-check`；machine-detector 附输入面与确定性通过/命中条件；protocol-check 附走查输入面与信号清单（承接检测器六字段中的 Rendered/Source signals） | check-type 枚举可查 |
| 10 | `evidence` ◆ | 证据形态（evidence modality） | `layers ⊆ {source, rendered, interaction, measurement}`（#29 四层）+ 每层最少条数 + 方法语义引用（method 枚举对齐 #29 §3.3） | 是 |
| 11 | `severity-default` ◆ | 缺省严重度（default severity） | `S3 \| S2 \| S1`（+ `S0` 正向观察类）+ 事实/判断类别标注（判断类永不 blocking，#29-Q8）；检测器行自身仍不判 severity（ADR-0014），本字段是给 evaluator 的缺省建议 | 是 |
| 12 | `exceptions` | 例外条件（legitimate exceptions） | 规则内生的合法例外，每条附判定依据声明（spec/已验证基线/领域惯例）——承接检测器六字段中的 Legitimate exceptions | 否 |
| 13 | `false-positives` | 误报条件（false-positive conditions） | 已知误报形态、规避方式与已记录误报计数引用（#24-Q4 点名） | 否 |
| 14 | `owner` ◆ | point-back owner | 第一跳：声明工件名（值域 = 回流映射的八工件 + 绑定基线路径）；第二跳：缺省 R1-R5 路由（可多值）——承接检测器六字段中的 Owner hint 并升为双跳 | 是（值域校验） |
| 15 | `provenance` ◆ | 来源（provenance） | `first-party \| promoted-from-findings \| placeholder \| benchmark-input-only` | 是 |
| 16 | `status` ◆ | 状态（status） | `draft \| advisory \| machine-enforced \| deprecated`（生命周期见 §2） | 是 |
| 17 | `fix` | 正向修复指引（positive fix） | 承接检测器六字段中的 Positive fix；禁无主禁令（须指向可执行编辑） | 否 |
| 18 | `related` ◆ / `overrides` ◆ | 关联 / 覆盖链接 | 其他规则 `ID@version` 列表；`overrides` 声明裁决序中的显式覆盖关系（G8 查无环，见 §3） | 是（引用存在性、无环） |
| 19 | `supersedes` ◆ | 取代（supersession） | 破坏性修订时指向旧 `ID@version`（见 §4） | 是（引用存在性） |
| 20 | `history` | 修订史（revision history） | `(version, 日期, 变更类型 breaking/refine/docs, 说明)` 列表 | 否 |

### 1.2 关键字段语义

- **provenance 四值（外部参考显式无权威的落点）**：
  - `first-party`：第一方独立撰写并验证（craft 八检测器、无障碍/响应式首版条目属此）。
  - `promoted-from-findings`：从重复发现经用户裁决晋升（§5），必须链接裁决记录。
  - `placeholder`：占位规则——适用谓词与证据形态已定义、检查定义未成形（首版仅 protocol-check 骨架或空）；执行时**永不静默跳过**：谓词求值 applicable 则按可用证据走查，证据不可得记 blocked（#24-Q5）。
  - `benchmark-input-only`：条目存在仅因外部参考样本比对暴露的能力缺口，或正文尚未完成第一方独立验证；**不拥有规则解释权**——不得直接晋升 machine-enforced，晋升前必须重新撰写并验证为 `first-party` 或走 `promoted-from-findings` 通道（provenance 变更是晋升裁决的一部分）。外部来源名与第三方规则原文永不进入注册表。
- **authority 与 status 正交**：权威级别描述规则主张的来源强度（冲突裁决序的输入，§3）；状态描述当前执行力（是否参与评审、命中能否参与 blocking）。占位规则可以持有 `hard-constraint` 权威（如安全体验底线）——占位只意味着检查定义未成形，不降低权威主张；项目声明不得因其占位而覆盖之。
- **applicability 谓词输入**（封闭清单，防执行方即兴发明）：run 类型（implemented UI / planning-only）；契约字段（含检测器启用子集声明，如 `craft.detectors`，未声明 = 该家族全目录启用）；spec 层声明（L4 异步操作、L1 多语言用户等）；证据面可用性（capture provider 在场与否）。三态求值语义沿用 #29 §1.3：`not-applicable` 必附可观察理由（空白 not-applicable 与空白 N/A 同罪）；`blocked` = 证据不可得的显式记录，不是失败也不是跳过。
- **evidence 最低要求**：`check-type: machine-detector` 条目必须声明确定性输入面与最少证据条数（craft 条目 = rendered + source 各 ≥1，缺任一即 blocked）；`protocol-check` 条目至少声明一层可用证据与「证据不可得 → blocked」出口。measurement 层结论必须绑定具体用户/任务/环境（无上下文数字门禁显式禁止，矩阵 D7）。
- **例外（exceptions）与豁免（exemption）是两回事**：`exceptions` 是规则内生的合法例外（判定它例外的事实依据来自声明）；豁免是绕过规则的显式决定，不属于条目正文，其语义见 §1.3。
- **owner 双跳**：第一跳承接现有 recirculate map（检测器 Owner hint 的 `craft/template/components/design` 即声明工件名）；第二跳给缺省 R1-R5 路由。多主发现允许多值（#29 §8.1 最小 owning 集语义照搬）。

### 1.3 豁免（exemption）语义（决议 Q4=A：双层豁免）

| 豁免类型 | 谁可授 | 记录什么 | 过期 |
| --- | --- | --- | --- |
| **run 级豁免**（advisory 规则） | 代理可记录 | 检测器行 / point-back finding 内：规则 `ID@version` + 可观察理由 + 证据引用；空白理由非法（沿用「N/A requires an observable reason」纪律） | 随 run 归档自然失效（不跨 run 存活） |
| **持久豁免**（machine-enforced 规则） | **仅用户**（= 接受风险，对齐 #24-Q7「blocking 处置仅当改变声明或接受风险时用户介入」） | 治理日志（§5.3）：规则 `ID@version` + 理由 + 风险陈述 + 接受时间；项目级持久豁免同步写入决定日志（`field` = 规则 ID，id 规则兼容） | 无日历 TTL（CONTEXT「Avoid calendar-only expiry」）；仅由结构事件触发复核：规则修订（version bump）、被取代、或豁免所依声明变更 |

evaluator 不得豁免自己的失败（Q7 既有）；`deprecated` 条目的历史豁免记录保留供审计。（决议 Q4=A，2026-08-14：双层豁免——advisory 代理 run 级、machine-enforced 仅用户记治理日志；无日历 TTL。）

---

## 2. 状态生命周期（工单项 2）

```
draft ──发布/裁决──▶ advisory ──用户裁决（六条标准）──▶ machine-enforced
  ▲                                                    │
  │                                                    │ 用户裁决 / 代理提议+用户裁决
  └────────── deprecated ◀──降级/废弃──────────────────┘
```

| 迁移 | 触发权 | 条件与记录 |
| --- | --- | --- |
| draft → advisory | 第一方：产品发布流程（随插件分发）；晋升通道：候选经用户裁决（§5） | 条目通过 G8 自校验（§8）；provenance=placeholder 条目可直接以 advisory 发布（Q5 锁定），其「未成形」由 provenance 表达而非状态 |
| advisory → machine-enforced | **仅用户裁决**（#24-Q7 锁定） | 六条晋升标准逐条满足并记录（§5.2）；同时要求 check-type 已是 machine-detector 或可确定性执行的 protocol-check、误报/漏报成本已评估、例外与豁免机制在位 |
| machine-enforced → advisory（降级） | 用户裁决；**代理可提议**（提议进入候选队列，永不自动生效） | 误报证据（false-positives 计数）或权威来源失效；降级记录入治理日志；受影响 run 的回归验证义务见 §5.4 |
| 任意 → deprecated（废弃） | 用户裁决；代理可提议 | 被取代（`supersedes` 指向新 ID）或权威来源撤销；条目保留（历史 finding 引用可解析），不再执行；`status: deprecated` 条目 G8 仍校验引用完整性 |

- 计数机器、迁移永不自动（D8 锁定）；draft 条目不参与评审执行（registry-only 执行面），但 G8 校验其形状。
- 首版注册表装态：craft 八条 = advisory / first-party；无障碍 + 响应式首版条目 = advisory / first-party（#29 §1.3 已定义证据面）；国际化 / 性能感知 / 安全体验 = advisory / placeholder（§7）。

---

## 3. 冲突解决（工单项 3）

### 3.1 裁决序（authority ordering）

两条规则对同一可观测量给出矛盾判定时，按权威级别从高到低裁决：

```
hard-constraint（硬约束：安全底线、无障碍可达性底线）
  > project-declaration（项目声明：持久契约、spec、已验证设计基线）
    > measured-threshold（实测阈值：仅在绑定具体用户/任务/环境的声明范围内有效）
      > platform-convention（平台惯例：目标平台成文惯例，Web 首验证面）
        > advisory-aesthetic（建议美学：通用工艺审美，最弱）
```

对齐依据：矩阵 D7 锁定「项目声明可覆盖建议美学，但不得覆盖硬约束（无障碍/安全需要独立权威级别，而非更强的措辞）」；ADR-0014「安全、可用性与显式声明高于基线一致性；已验证基线胜过通用检测器审美」；CONTEXT 持久契约 = 唯一持久决定权威。推论：

- 项目声明内部冲突（契约 vs 已验证基线）：契约优先（持久决定权威），基线其次；冲突本身是 finding，回流 owning 声明。
- 实测阈值脱离声明上下文 = 无效主张（「无上下文数字门禁显式禁止」），不能压制平台惯例。
- 通用检测器审美（craft 条目）不覆盖已验证基线——craft-guard 技能既有让位规则原样保留为条目语义。

### 3.2 重叠（非矛盾）与同 severity 冲突

- **重叠**（两条规则命中同一可观测量、修复方向一致）：finding 去重按 observable（非按规则）；每条 finding 的 `rule:` 行列出全部涉及 `ID@version`，主裁规则列首位；注册表侧以 `related:` 预声明已知重叠。
- **矛盾且权威级别不同**：高者裁决；被压制规则的命中仍记录（`rule:` 行 + `superseded-by-authority:` 注记）——压制不等于删除证据。
- **矛盾且同 severity / 同权威级别**：**永不静默择一**。事实类 → 双 finding 交叉引用 + 按缺省 R 路由回流 owning 声明，由声明修订消解；判断类 → 走 #29 §4.4 呈报通道三选一（改声明 / 接受风险 / 提交 D7 晋升队列）。
- **注册表侧预声明**：`overrides:` 链接显式声明已知覆盖关系；G8 校验覆盖图无环（§8）。环 = 注册表自身缺陷，阻断发布而非运行时裁决。

### 3.3 记录义务

- finding 的 `rule:` 行（附加字段行，现有解析器忽略，向后兼容）列出全部涉及规则 `ID@version`；机器强制规则的压制/裁决必须引用所用裁决序条款（如 `authority: hard-constraint > project-declaration`）。
- 冲突消解若改变了规则语义 → 走版本化（§4）修订，禁止在 finding 里临时发明第三规则。

---

## 4. 版本化（工单项 4）

- **条目级修订号**：`version` 正整数；`refine`（信号/例外/修复指引细化，语义不变）与 `docs`（文案）变更 bump 版本；**破坏性修订（适用谓词收窄/放宽、severity 缺省变更、检查语义变更）不改动原条目，而是新建 ID 并以 `supersedes` 指旧条目**——稳定 ID 的含义必须稳定，与 decisions.jsonl「修订永不改写历史」同构。
- **引用钉版本**：检测器审计行与 finding 的 `rule:` 行引用 `ID@version`（如 `CRAFT-01@3`）；ledger 行不引用规则（ledger 只对 L6 criterion 负责，检测器行不进 ledger——既有边界不动）。治理日志、豁免记录、候选条目同样钉 `ID@version`。
- **注册表级 `schemaVersion`**：注册表文件自带整数 schema 版本（字段集变更时 bump；旧读取方忽略未知字段——与 manifest 方法语义键同一兼容哲学）。
- 版本化方案已定（决议 Q3=A，2026-08-14）：**条目修订号 + 破坏性修订换新 ID（supersedes），引用一律钉 `ID@version`**——与 decisions.jsonl「修订永不改写历史」同构，稳定 ID 承担语义稳定。

---

## 5. 晋升协议（工单项 5；协议定义，不实现闭环——#24-Q6=B）

### 5.1 D8 候选队列的信号形态

信号 = **带上下文的重复发现**，不是无上下文计数（D8 锁定）。首版信号从既有 run 记录**派生**（#28 先例：读历史、不新增持久状态），派生输入 = `aggregate_runs.py` 的 repeat blocker 面（归一化 observed 文本 + distinct run 计数）+ 各 run point-back 的 finding 附加字段（track/severity/confidence/evidence）。候选条目 schema：

```json
{"candidate_id": "CAND-2026-34-01",
 "signal_key": "<归一化 observed/issue 文本>",
 "occurrences": [
   {"run": "<run id>", "date": "2026-08-14",
    "track": "interaction", "severity": "S2", "class": "fact",
    "confidence": "high",
    "context": {"user": "<l1.target_user 引用>", "task": "<L6/主路径节点引用>",
                 "environment": "<viewport/平台/数据集>", "method": "runtime-observation"},
    "evidence": "<artifact 路径或源码引用>"}],
 "distinct_runs": 3, "distinct_task_contexts": 2,
 "false_positive_notes": "误报记录或空",
 "suggested_rule": {"id": "ST-01", "family": "ST", "statement": "...", "severity-default": "S2"},
 "status": "candidate | promoted | rejected | merged | deferred",
 "adjudication_ref": "<治理日志事件 id，裁决后回填>"}
```

- 派生规则：同一 `signal_key` 跨 distinct runs 计数；context 字段从契约/spec/manifest 方法语义键取值——**上下文不同的重复不合并**（不同用户/任务的相同表象可能是不同规则）。
- 候选资格门槛已定（决议 Q5=A，2026-08-14）：**distinct runs ≥3 且 任务语境 ≥2 种 且 未解释误报 =0** 方可入队（进入队列的最小条件，非晋升条件；晋升另按 §5.2 六条标准 + 用户裁决）。数值可随 D8 跨 run 信号调整（同 #28-Q3 的保留条件精神）。

### 5.2 晋升标准（矩阵原则 3 的六条 → 可判条目）

候选 → advisory 或 advisory → machine-enforced 的每条裁决记录必须逐条满足并留证：

| # | 标准（原则 3 原文） | 可判条目（裁决记录中必须指向的证据/字段） |
| --- | --- | --- |
| 1 | 权威来源 | `authority` 级别 + 其来源声明（平台成文惯例 / 项目声明 / 领域底线）引用 |
| 2 | 对应用户可见风险或产品不变量 | `statement` 的用户影响半句 + 受影响 L6/主路径节点引用 |
| 3 | 输入与通过条件确定可复现 | `applicability` 谓词 + `check` 的确定性输入面与命中条件；check-type 为 machine-detector（machine-enforced 晋升的必要条件） |
| 4 | 误报/漏报成本已评估 | `false-positives` 字段 + 候选中误报记录 + 显式成本陈述（漏报后果 vs 误报摩擦） |
| 5 | 存在修复路径与例外机制 | `fix` + `exceptions` + 豁免机制引用（§1.3） |
| 6 | 已通过内部样本与反例验证 | 内部 run 样本集（命中确认）+ 反例集（明确不命中确认）的 run id 清单 |

advisory 晋升（候选 → 注册表 advisory 条目）可用较弱的面板（标准 1/2/4 + provenance=promoted-from-findings）；**machine-enforced 晋升六条全过且仅用户**（#24-Q7）。

### 5.3 用户裁决记录格式（治理日志，append-only）

治理日志事件（首版定义 schema，落码归 #32；载体已定——决议 Q7=A：项目级 append-only `rules-governance.jsonl`，与持久契约同层，只记用户决定性事件，候选视图从 run 历史派生）：

```json
{"event": "adjudicated", "candidate_id": "CAND-2026-34-01",
 "rule_id": "ST-01", "target_version": 2, "target_status": "machine-enforced",
 "decision": "promote", "decided_by": "user", "confirmed_at": "2026-08-14T00:00:00Z",
 "criteria": {"authority": "...", "risk": "...", "reproducible": "...",
               "fp_cost": "...", "fix_path": "...", "validation": "..."},
 "supersedes": null}
```

事件枚举：`candidate_opened / evidence_appended / adjudicated(promote|reject|merge|defer) / rule_revision / exemption_granted / exemption_reviewed`。与决定日志同构：append-only、id 稳定、supersedes 指向已存在条目；`decided_by: user` 不可由代理写入（沿用 G7「不宣称证明用户身份，但结构上区分用户确认与代理记录」的边界）。

### 5.4 晋升后回归验证义务（首版仅定义）

- machine-enforced 晋升后的首个 run：规则必须在新 run 上执行并记录首个正式检测器行/finding（证明执行力在位）。
- 降级/废弃：受影响历史 run 不重写（append-only 哲学）；治理日志记录受影响规则集；下一个 run 起按新状态执行。
- 反例集回归：规则每次破坏性修订（新 ID）须附反例集 run 清单（标准 6 的持续形态）。
- 以上均为**义务定义**；闭环执行（自动追踪、提醒、验证 run 编排）延后（#24-Q6=B）。

---

## 6. craft-guard 迁移方案（工单项 6）

### 6.1 八检测器逐条映射（ID 原样保留——已发布 ID 与 fixture 引用不破坏）

统一底座：capability-domain = D4、executes-in = D4:interaction（工艺面）、authority = advisory-aesthetic（通用工艺审美，可被项目声明/已验证基线覆盖）、status = advisory、provenance = first-party、check-type = protocol-check（首版无 machine-detector；渲染+源码双面代理走查，ADR-0014 边界保留）、evidence = rendered ≥1 且 source ≥1（缺任一 → 谓词 blocked）、豁免 = run 级带理由。

| ID | 名称 | 适用谓词要点 | severity-default | 例外（exceptions 要点） | owner（第一跳 → 缺省第二跳） |
| --- | --- | --- | --- | --- | --- |
| CRAFT-01 | 主视觉层级（primary hierarchy） | run 有 Fill 产物且表面含可声称主次的动作/区域；planning-only → not-applicable(附理由) | S2 判断类 | spec/已验证基线支持的有意等权选择 | craft → R4；模板组合致冲突时 template → R4/R3 |
| CRAFT-02 | 重复卡片墙（repeated card wall） | run 有 Fill 产物且存在列表/集合展示面 | S2 判断类 | 可浏览独立对象集合且基线用卡 | template → R4；视觉加权 craft → R4 |
| CRAFT-03 | 嵌套/悬浮容器（nested containers） | run 有 Fill 产物且存在分区/容器组合 | S2 判断类 | 真实带框工具、模态、无框区内重复项 | template → R4；原始件误用 components → R4 |
| CRAFT-04 | 单色调色板（one-note palette） | run 有 Fill 产物且存在多语义表面 | S2 判断类 | 已验证单色品牌系统（状态/对比/层级足辨） | design（令牌角色）→ R3；craft → R4 |
| CRAFT-05 | 形状/胶囊滥用（shape overuse） | run 有 Fill 产物且存在控件/标签几何面 | S1 判断类 | 已验证品牌几何；语义 chip/tag | components → R4；design（圆角令牌）→ R4 |
| CRAFT-06 | 字号失配（type-scale mismatch） | run 有 Fill 产物且存在密集容器排版 | S1 判断类 | 真实落地页 hero；已验证表现型表面 | design（字型角色）→ R4；craft → R4 |
| CRAFT-07 | 文本当控件/图标误用（text-as-control） | run 有 Fill 产物且存在高频重复操作面 | S2 判断类 | 生僻/高危/歧义动作需显式文字；图标无障碍名仍必需 | components → R4；craft → R4。注：可访问名缺失子信号是事实类，evaluator 依 #29 分轴可独立定级 |
| CRAFT-08 | 无目的动效（purposeless motion） | run 有 Fill 产物且存在动效；动效源/交互轨迹缺失 → blocked（现行 blocked 高发点，显式化） | S2 判断类 | 声明的产品表现型场景动效且远离任务控件 | craft → R4；design（动效令牌）→ R4 |

（六字段块的其余内容——Purpose/Rendered signals/Source signals/Positive fix——逐条并入新条目的 statement / check 信号清单 / fix 字段，文本为第一方原创，原样迁移。）

### 6.2 状态枚举矛盾的修复（N/A 并入三态求值）

矛盾根因：单一 Status 列同时承担「规则是否适用」（N/A）与「检查结果/证据是否可得」（clear/hit/blocked）两个正交语义。修复 = **拆列**，对齐 #29 适用谓词三态求值：

新审计行格式（`.scratch/<run>/craft-guard.md`，工件名与 stage registry 不变）：

```text
| ID@ver | Applicability | Predicate reason / missing proof | Result | Rendered evidence | Source evidence | Exception check | Positive fix |
```

| 旧值 | 新落点 | 语义 |
| --- | --- | --- |
| `clear` / `hit` | `Applicability: applicable` + `Result: clear\|hit` | 检查已执行 |
| `N/A`（带理由） | `Applicability: not-applicable` + 理由列 | 规则不适用本 run，**永不静默**（空白理由非法，沿用既有纪律）；对齐 #29 三态的 not-applicable(附理由) |
| `blocked`（缺证据） | `Applicability: blocked` + 缺失证明说明列 | 证据不可得（如动效源未入评审输入）；对齐 #29 三态的 blocked(证据不可得)，craft proof gap 照旧带入评审 |

- `Result` 仅 applicable 时必填，否则为 `-`；`Positive fix` 仅 hit 时必填（现行规则）。
- 归一化语义：旧三值/四值写法在新格式下**不再合法**；历史 run 工件不重写（append-only 哲学），新格式自迁移后的 run 生效。

### 6.3 craft-guard 技能降级为引用/执行说明层的具体改法（清单，不执行）

1. 检测器目录迁出：`craft-guard/references/detectors.md` 的八条六字段块整体迁入注册表（条目化 + 治理字段），`detectors.md` 改为薄引用层（指向注册表 + 行格式 + 执行说明），或直接删除并让 SKILL.md 指向注册表——二选一随载体决策（Q2）。
2. `craft-guard/SKILL.md`：「AI slop → target look」段的行格式说明改为新七列格式与三态语义；启用子集机制（契约声明 `craft.detectors` 类字段 / 缺省全目录）改述为「注册表条目的适用谓词输入」；hierarchy/loading tiers/motion 三段工艺清单**保留在技能内**（它们是 craft 声明本体，不是注册表规则）。
3. `ui-evaluator/SKILL.md` 消费段：「eight rows」「N/A rate」措辞改为「注册表中适用谓词求值为 applicable 的 craft 条目恰一行」；警告条件改为「全 applicable 子集为 not-applicable，或任一 not-applicable 缺理由，或 blocked 率异常」；「检测器永不决定 source/severity/verdict」「永不进 manifest/ledger」两句原样保留。
4. fixture 迁移（四份，均改行格式并补 Applicability 列）：`examples/craft-detectors/saas-dashboard.md`（八行齐全，含 not-applicable 与 blocked 演示——现行 CRAFT-08 blocked 行改为 `Applicability: blocked`）、`composition-contrast.md`、`landing-product-contrast.md`、`existing-brand-contrast.md`。
5. `scripts/validate.py`：检测器契约段重写为注册表条目段（G8 产品级校验，§8）；fixture 行形状正则改七列；新增注册表自校验清单。
6. `packages/design-playbook/scripts/stages.py`：无改动（`craft-guard.md` 工件名不变）。
7. G2-G4/G6/G7：无改动（检测器行不在其消费面）。

---

## 7. 占位规则（工单项 7）：三条完整示例

占位条目 = status: advisory + provenance: placeholder + check-type: protocol-check（骨架）+ 显式适用谓词（三态）+ 证据不可得 → blocked。首版交付即进注册表（#24-Q5）。

```yaml
id: I18N-01
version: 1
title: 界面语言与可本地化一致性（interface language & localizability consistency）
statement: 用户可见文案的语言/术语/格式一致且不阻碍本地化（可观测量）；
           不一致的术语与硬编码格式增加本地化与理解成本（用户影响）
capability-domain: D4
executes-in: D4:cross-cutting
authority: platform-convention
applicability:
  predicate: >
    applicable 当：契约声明多语言/i18n 字段（如 i18n.*）或 spec L1 声明多语言用户群；
    not-applicable（附理由）当：单语声明且无 locale 相关字段（理由示例：单语文档界面，无 i18n 声明）；
    blocked 当：判定所需的文案清单证据不可得（如渲染采集缺席）
check:
  type: protocol-check
  inputs: [rendered 文案采样, source 硬编码文案定位, spec L1 术语表]
  signals: 术语混用 / 硬编码日期数字格式 / 布局不可容纳文案膨胀（骨架，未成形）
evidence:
  layers: {rendered: 1, source: 1}
  method: static-inspection 或 runtime-observation
severity-default: S2 判断类
exceptions: 声明的单语产品且用户群确认单语
false-positives: 代码内注释与开发者面文案（非用户可见）——待验证
owner: spec → R2（术语/声明缺口）；components → R4（实现层文案散落）
provenance: placeholder
status: advisory
fix: 统一术语到 spec L1 词表；用户可见文案经资源层而非硬编码
related: []
```

```yaml
id: PERF-01
version: 1
title: 操作性能感知反馈（perceived-performance feedback）
statement: 声明的异步操作有与耗时相称的感知反馈与超时出口（可观测量）；
           无反馈的等待引发重复触发与不信任（用户影响）
capability-domain: D4
executes-in: D4:cross-cutting
authority: measured-threshold   # 仅在绑定具体任务/环境的声明范围内有效；无上下文数字门禁禁止
applicability:
  predicate: >
    applicable 当：spec L4 声明异步操作 且 run 的 measurement 层可采；
    blocked 当：异步声明存在但度量 provider 缺席（理由示例：性能感知需运行时度量，provider 缺度量面）；
    not-applicable（附理由）当：无异步操作声明
check:
  type: protocol-check
  inputs: [measurement 派生计时, interaction 轨迹, spec L4 声明]
  signals: 无反馈长等待 / 反馈与耗时不匹配 / 无超时出口（骨架）
evidence:
  layers: {measurement: 1, interaction: 1}
  method: runtime-observation
severity-default: S2 判断类   # 阈值判断须绑定任务；事实类子信号（如超时死端）由 evaluator 依分轴定级
exceptions: 声明的后台任务以完成通知而非行内反馈
false-positives: 短于感知阈的操作被要求反馈——待验证
owner: spec → R2（L4 状态声明缺口）；evidence plan → R5（度量面缺席）
provenance: placeholder
status: advisory
fix: 按耗时分层反馈（与 craft 声明 Loading tiers 对齐；裁决序按 authority，实测阈值在声明范围内高于建议美学）
related: [CRAFT-08@1]
```

```yaml
id: SEC-01
version: 1
title: 敏感操作安全体验（sensitive-operation safety experience）
statement: 敏感数据与危险操作有确认、撤销或审计出口（可观测量）；
           无防护的危险操作造成不可逆损失（用户影响）
capability-domain: D4
executes-in: D4:cross-cutting
authority: hard-constraint   # 权威与状态正交：占位不降低权威主张，项目声明不得覆盖
applicability:
  predicate: >
    applicable 当：domain/spec 声明敏感数据或危险操作（domain 风险语义）；
    not-applicable（附理由）当：声明范围无敏感面（理由示例：无敏感操作新增）；
    blocked 当：敏感性无法从既有声明判定（声明缺口本身是 finding，回流 D1）
check:
  type: protocol-check
  inputs: [interaction 危险操作轨迹, source 确认/撤销绑定, domain 声明]
  signals: 危险操作无确认 / 无撤销或审计 / 敏感值明文暴露（骨架）
evidence:
  layers: {interaction: 1, source: 1}
  method: runtime-observation
severity-default: S3 事实类   # 事实类命中可 blocking 的候选；本条首版 advisory（未晋升），
                             # 判断类子信号永不 blocking（#29-Q8）
exceptions: 声明的受控环境演练操作（须有 domain 声明依据）
false-positives: 已有全局撤销栈的操作被要求二次确认——待验证
owner: domain → R1（风险语义声明缺口）；implementation → R4（防护缺失）
provenance: placeholder
status: advisory
fix: 危险操作加确认/撤销；敏感值脱敏呈现；审计出口入 domain 声明
related: []
```

（无障碍 + 响应式首版**实**条目 A11Y-01 / RESP-01 同 schema：provenance=first-party、以 a11y tree capture 与 capture contract viewport 组为主证据，证据面与附接规则按 #29 §1.3 已定稿表述，本文不重复展开。）

---

## 8. 注册表载体与自身校验（工单项 8）

### 8.1 载体（决议 Q2=A：单文件 markdown 字段块，管线级共享声明位）

- **单文件 markdown，条目 = 结构化字段块**：位置已定——`packages/design-playbook/skills/design-playbook/references/rules.md`（编排技能持有管线级共享声明，与 stage registry「一个家、一个漂移面」ADR-0021 哲学一致）；条目块沿用 `detectors.md` 六字段块 + `scripts/validate.py` 正则校验的既有模式（已验证可机器校验的 markdown 声明风格）。**增长触发拆分条件**（写入注册表头部说明）：条目数超过 30 或家族数超过 3 时，按家族拆分文件 + 索引；拆分时 G8 跨文件校验一并迁移。（后注：已交付注册表为 20 条 / 8 家族（#101-#105 吸收批后）——家族数已越此线，但 Q2 与 #33 首切片的单文件裁定优先生效，现届**有意维持单文件**；家族触发器留作日后拆分时机的参考，不构成既成违例。）
- **机器可查面 / 协议面边界**：机器可查面 = §1.1 全部 ◆ 字段（id/version/enums/owner 值域/引用链接/supersedes）；协议面 = statement/check 信号/exceptions/false-positives/fix/history 文本。G 门禁只校验前者；后者由评审技能与裁决者消费。
- 注册表是**产品级声明工件**（随插件分发、read-only 于 run）：不进 `.scratch/<run>/`、不进 manifest、不被 run 写入；run 侧只产出引用它的审计行与 finding。

### 8.2 G8：注册表完整性门禁（gate，首版产品级）

G1-G7 编号已占用；注册表自校验命名 **G8**。范围已定（决议 Q6=A，2026-08-14）：首版做**产品级完整自校验**，run 级覆盖检查延后 #32。两级：

- **产品级（首版，落点 = `scripts/validate.py` 扩展，替代现行检测器契约段）**：ID 唯一且合格式；status/authority/provenance/severity-default/check-type 枚举合法；owner 第一跳 ∈ 回流映射八工件 ∪ 绑定基线、第二跳 ∈ R1-R5；`related/overrides/supersedes` 引用存在且覆盖图无环；version 单调；每个 machine-enforced 条目有治理日志裁决引用与六条标准记录；每个 placeholder 条目有 applicability 谓词与 blocked 出口；正文内容 lint（不出现外部产品名与第三方规则原文——见本仓库内容禁令）。
- **run 级（延后至 #32，随 #29-Q7 同批机器化）**：`.scratch/<run>/craft-guard.md` 覆盖检查——注册表中适用谓词求值为 applicable 的 advisory 条目恰有一行；行值域符合七列格式。首版此检查由技能协议执行（同 #29 Coverage 进最小门禁、Limitations 协议消费的分层）。

---

## 9. 走查示例（工单项 9）

### 9.1 迁移条目全文两例（CRAFT-01 与 CRAFT-08）

```yaml
id: CRAFT-01
version: 1
title: 主视觉层级（primary hierarchy）
statement: 每视口恰一主行动/主区域引导扫视（可观测量）；
           多主或无主使目标用户无法一眼定位首要动作（用户影响）
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
applicability:
  predicate: >
    applicable 当：run 有 Fill 产物且表面含可声称主次的动作/区域（契约检测器子集未禁用本条）；
    not-applicable（附理由）当：planning-only run 或纯展示无动作面；
    blocked 当：rendered 或 source 任一证据面不可得
check:
  type: protocol-check
  inputs: [rendered 界面走查, source 主次变体与令牌使用]
  signals:
    rendered: 多元素同争主强调，或无行动/区域引导扫视
    source: 多 primary 变体、等强强调令牌、页面结构无主 landmark
evidence:
  layers: {rendered: 1, source: 1}
  method: expert-review（代理走查须显式声明，finding 仅 advisory）
severity-default: S2 判断类
exceptions: spec 或已验证基线支持的有意等权比较（如并排方案选择页）
false-positives: 已验证基线的双主布局（基线优先于通用审美，记录于例外）
owner: craft → R4；模板组合致冲突时 template → R4/R3
provenance: first-party
status: advisory
fix: 保留一个场景相称的主行动；次级行动以位置/密度/中性处理退后
related: [CRAFT-06@1]
```

```yaml
id: CRAFT-08
version: 1
title: 无目的动效（purposeless motion）
statement: 每个动效命名其解释的状态变化且不干扰交互（可观测量）；
           无状态解释的动效吸走注意并 destabilize 操作（用户影响）
capability-domain: D4
executes-in: D4:interaction
authority: advisory-aesthetic
applicability:
  predicate: >
    applicable 当：run 有 Fill 产物且存在动效；
    blocked 当：动效源或交互轨迹未入评审输入（现行高发 blocked，显式化为谓词语义）；
    not-applicable（附理由）当：表面无动效
check:
  type: protocol-check
  inputs: [rendered 动效观察, source 动效实现与 reduced-motion 处理, interaction 轨迹（可得时）]
  signals:
    rendered: 弹跳/回弹/循环/入场动效不传达状态
    source: 动画目标为布局属性、缺 reduced-motion 处理、无命名状态转移
evidence:
  layers: {rendered: 1, source: 1}
  method: expert-review
severity-default: S2 判断类
exceptions: 声明的表现型场景动效（游戏/沉浸）且远离任务控件
false-positives: 微交互过渡被误判为装饰——以「是否命名状态变化」判定
owner: craft → R4；design（动效令牌）→ R4
provenance: first-party
status: advisory
fix: 移除装饰动效，或替换为绑定命名状态变化的短时 transform/opacity 反馈
related: [PERF-01@1]
```

（CRAFT-07 等其余六条按 §6.1 表同构展开，不赘。）

### 9.2 纸面晋升流程：重复发现 → advisory → machine-enforced（含用户裁决记录）

**背景信号**：#29 §9.2 的同型事实类发现——「导出进行中触发按钮无 busy/disabled 态，可重复触发并发导出」（track: interaction、S2、confidence: high、interaction+source 跨层证据）——在 3 个 distinct runs、2 种任务语境（数据导出 / 批量删除）重复出现。

1. **D8 派生**：run 聚合按归一化 issue 文本聚合 3 次出现（上下文各自保留：用户/任务/环境/方法四字段来自契约与 manifest 方法语义键）→ 满足候选资格（Q5=A 阈值：distinct runs ≥3 且任务语境 ≥2 且未解释误报 =0）→ `candidate_opened` 事件写入治理日志，候选 `CAND-2026-34-01`（形态 §5.1）。
2. **第一次用户裁决（候选 → advisory）**：用户在评审报告「待用户裁决」子块（#29-Q5 通道）选择「提交 D7 晋升队列」后裁决 **promote**。新条目入注册表：

```yaml
id: ST-01
version: 1
title: 异步操作进行中的重复触发防护（in-flight re-trigger guard）
statement: spec L4 声明的异步操作进行中，其触发控件有 busy/disabled 态且不可重复触发（可观测量）；
           重复触发产生重复副作用（重复导出/重复删除），用户可见且可能不可逆（用户影响）
capability-domain: D4
executes-in: D4:interaction
authority: platform-convention
applicability:
  predicate: applicable 当 spec L4 声明异步操作；not-applicable（附理由）当无异步声明；
             blocked 当交互轨迹不可得且源码不足以判定
check:
  type: protocol-check
  inputs: [interaction 轨迹（连续触发复现）, source 触发器 disabled/busy 绑定]
  signals: {interaction: 轨迹显示进行中二次触发成功, source: 触发器无 busy/disabled 绑定}
evidence: {layers: {interaction: 1, source: 1}, method: runtime-observation}
severity-default: S2 事实类
exceptions: 声明了幂等的操作（幂等声明入契约，豁免走 run 级带理由）
false-positives: 幂等操作（3 run 0 误报；幂等已列为例外）
owner: spec → R2（L4 状态转移声明缺口）；implementation → R4（绑定缺失）
provenance: promoted-from-findings
status: advisory
fix: 进行中置 busy 并禁重复触发，完成后恢复；补 L4 状态行
related: [PERF-01@1]
```

   裁决记录（治理日志）：`{event: adjudicated, candidate_id: CAND-2026-34-01, rule_id: ST-01, target_version: 1, target_status: advisory, decision: promote, decided_by: user, confirmed_at: <ts>, criteria: {authority: platform-convention（平台交互惯例+契约异步声明）, risk: 重复副作用, fp_cost: 0 误报/幂等例外在位}, supersedes: null}`。

3. **证据续积**：advis0 状态执行 2 个新 run：命中确认 2 次、反例 1 次（声明幂等的批量操作正确不命中——例外机制验证）；check 的输入面与命中条件被证明确定可复现（interaction 轨迹 + source 绑定双证据）。
4. **第二次用户裁决（advisory → machine-enforced，六条标准全过）**：

```json
{"event": "adjudicated", "candidate_id": "CAND-2026-34-01", "rule_id": "ST-01",
 "target_version": 2, "target_status": "machine-enforced", "decision": "promote",
 "decided_by": "user", "confirmed_at": "2026-08-14T00:00:00Z",
 "criteria": {
   "authority": "platform-convention + 契约异步操作声明（L4）——权威来源在位",
   "risk": "重复触发 → 重复导出/删除副作用，绑定 run-42 L6.1（限时导出判据）与 run-47 L6.2（批量删除确认）",
   "reproducible": "输入面确定：spec L4 异步声明 && 触发器源码无 busy/disabled 绑定 && interaction 轨迹可复现二次触发；命中条件机械可判（check 升格 machine-detector 路径已评估）",
   "fp_cost": "5 run 内 0 误报；漏报成本 = 不可逆副作用 > 误报摩擦（busy 态是标准惯例）；例外与 run 级豁免机制在位",
   "fix_path": "fix 指令（busy+禁重复触发）与 owning 声明回流路径（R2/R4）已定义",
   "validation": "内部样本集 run-41/42/47（命中确认）+ 反例集 run-48（幂等操作正确不命中）"},
 "supersedes": null}
```

5. **晋升后义务（定义，不执行）**：首个后续 run 必须记录 ST-01@2 的第一条正式机器执行结果；每次命中的事实类 finding 可按 #29 §4.3 组合表参与 blocking（S3 事实类 → blocking 进 G4 closure；S2 事实类 → advisory 进修复清单）；豁免自此仅用户（§1.3 持久豁免行）。

走查结论：候选 → advisory → machine-enforced 全链路中，机器只做了计数、派生与记录；两次状态跃迁都由用户裁决事件承载，六条标准以可查证据形式落在裁决记录内——与「计数机器、晋升永不自动」的 D8 锁定和 #24-Q7 决策权表一致。

---

## 10. 对后续工单的接口

| 工单 | 本原型交出的接口 |
| --- | --- |
| #31 | owner 第二跳 R3（design decision）的条目侧约定：rules 只给缺省路由，方案取舍细节归决策报告 schema |
| #32 | G8 两级门禁落码（产品级 validate.py 扩展清单 §8.2；run 级覆盖检查）；七列检测器行与 finding `rule:` 行的正式 schema；治理日志与候选条目 JSON schema 落地；旧 severity 别名换算（#29-Q1 既有移交）；fixture/校验脚本迁移执行（§6.3 清单） |
| #33 | 首切片最小注册表建议：craft 八条 + A11Y-01/RESP-01 实条目 + 三条占位（I18N/PERF/SEC）+ G8 产品级校验；晋升闭环执行不在首切片（#24-Q6=B） |
| D8 后续 | 候选队列事件枚举与裁决记录格式（§5）即学习域闭环的协议基座；闭环执行工单届时按此扩展 |

---

## 已确认决议（2026-08-14，用户裁决：全部按建议采纳）

| 题 | 问题 | 决议 |
| --- | --- | --- |
| Q1 | 规则 ID 格式（已发布 CRAFT-01…08 的处置） | **A：家族码-两位序号，CRAFT-01…08 原样保留**——新家族同构（A11Y-01/RESP-01/I18N-01/PERF-01/SEC-01/ST-01…）；ID 与能力域解耦（域由 capability-domain 字段表达）；已发布 ID、fixture 与技能文本零破坏；与 decisions.jsonl 的 id 正则兼容 |
| Q2 | 注册表载体位置与格式 | **A：单文件 markdown + 结构化字段块**，置于 `packages/design-playbook/skills/design-playbook/references/rules.md`（编排技能持有管线级共享声明）；~11 条起步单文件足够，超过 30 条或 3 个以上家族时按家族拆分 + 索引（拆分条件写入注册表头部说明） |
| Q3 | 版本化方案（语义化级别） | **A：条目修订号（整数）+ 破坏性修订换新 ID（supersedes）**——refine/docs 变更 bump 修订号；适用谓词/severity/检查语义变更 = 新 ID + supersedes 旧条目；引用一律钉 ID@version；与 decisions.jsonl「修订不改写历史」同构 |
| Q4 | 豁免语义（machine-enforced 规则的豁免权与过期） | **A：双层豁免**——advisory 规则代理可记 run 级豁免（附可观察理由，随 run 归档失效）；machine-enforced 规则豁免 = 接受风险，仅用户，持久豁免记治理日志并同步决定日志（field=规则 ID）；无日历 TTL，过期仅由结构事件触发（规则修订/被取代/所依声明变更） |
| Q5 | 晋升候选资格门槛（进入 D8 队列的数值条件） | **A：distinct runs ≥3 且 任务语境 ≥2 种 且 未解释误报 =0**（上下文不同的重复不合并）；advisory → machine-enforced 另需六条标准全过 + 用户裁决；数值可随 D8 跨 run 信号调整 |
| Q6 | G8 首版机器可查面范围 | **A：产品级完整自校验**（validate.py 扩展：ID 唯一/枚举/owner 值域/引用完整/覆盖图无环/machine-enforced 裁决引用/占位谓词存在 + 内容禁令 lint，替代现行检测器契约段）+ **run 级覆盖检查延后 #32**（随 #29-Q7 同批机器化，首版协议消费） |
| Q7 | 候选队列与治理记录的载体 | **A：append-only 治理日志（rules-governance.jsonl，项目级与持久契约同层）+ 候选视图从 run 历史派生**——日志只记用户决定性事件（开立/缓议/裁决/修订/豁免），不记可重算的计数；schema 首版只定义不实现（#24-Q6=B 锁定） |
