# UI/UX 实现评审与证据模型原型（Dual-track implementation review & evidence model — decision model prototype）

- 工单：#29（wayfinder:prototype）。域：D4 实现评审 IR（Dual-track implementation review）+ D5 证据 EV（Evidence binding & semantics），含 D6 失效语义接口。
- 状态：**已定稿**。2026-08-14 用户裁决：7 项待决问题全部按建议采纳（Q1-Q7，见文末「已确认决议」）。本文回答工单点名八项（评审维度、页面与流程覆盖、四层证据、严重度与置信度、正向发现、验证边界、报告形态、回流路由）+ 走查示例；正文按决议收敛表述。
- 性质：纸面决策模型（规划型地图产物）。不实现产品代码、不改技能与脚本；schema/门禁落码归 #30/#32。
- 上游锁定决议（不可推翻，只细化）：#24 矩阵 8 域与全局原则（证据两分、自动化默认立场、Provider 边界、按后果分级的决策权）；#24-Q5=A（首版横切 = 无障碍 + 响应式；国际化/性能感知/安全体验为 advisory 占位规则，显式适用谓词，不静默跳过）；#24-Q7=A（blocking 处置仅当改变声明或接受风险时用户介入）；#24-Q8=A（主观维度默认 advisory，晋升须先经规则治理或项目显式声明）；#28 成形模型定稿（S6 结束门禁、契约字段路径 `l1.*`/`l6.cN`、assumed 可见性义务、证伪回流重开子树机制）。
- HCI 硬约束贯穿全文：可复现事实可自动验证；主观与用户代表性结论必须人工证据；代理不得以自身评分替代用户证据；启发式命中不得直接判阻断缺陷、未命中不得判体验通过。

## 0. 真实 schema 基础（模型的落点，全部来自已交付代码）

模型只落到已存在的字段名与文件名，不发明平行 schema：

- **Evidence ledger 行**（`packages/design-playbook/mcp/evidence/ledger_syntax.py`）：四字段 `criterion: L6.<n>` / `required:` / `observed:` / `result:`；`result` 值域 `{pass, fail, blocked, n/a}`（`VALID_RESULTS`，G2-G4）；`observed` 既可是 run 根相对 artifact 路径（首 token，G6 只验证 `evidence/` 前缀者）也可是自由文本人工观察，两者合法；不可得的必备证据记 `blocked` 而非跳过。ledger 与 findings 同居于 `.scratch/<run>/point-back.md`（stage registry 的固定工件名）。
- **manifest 条目**（`.scratch/<run>/evidence/manifest.jsonl`，append-only，多条目 ts 最新者胜）：`{criterion, capture{type, provider, state, actions, schemaVersion, request}, artifact, observed_state, result:"captured", ts, request{schemaVersion, viewport{width,height,devicePixelRatio,colorScheme}, freeze{enabled,waitFonts,networkIdle}}}`。写入者是 orchestrator（provider 永不写 manifest）；capture contract v1（viewport/freeze）已内嵌。
- **finding 四字段**（ui-evaluator SKILL.md + G2）：`issue / source / fix / severity`，`severity` 现值域 `high (blocking)|high|med|low`；解析器 `_findings` 按段落块只提取四字段行——**块内附加行（如 `confidence:`）被自然忽略**，因此 finding 结构可向后兼容地扩展。
- **closure 行**（G4）：`- closes: <exact issue value> -> recirculate -> fix -> re-eval -> 0 blocking`；blocking 不得被删除通过。
- **verdict**：恰一 `## Verdict` 节，恰一锚定结论 `Pass | Recirculate`；Pass 需零 blocking + 每条 L6 恰一行证据 + 全部证据行 pass（G3）。
- **craft-guard 检测器表**：`| ID | Status | Rendered evidence | Source evidence | Exception check | Positive fix |`，CRAFT-01…08，状态 `clear|hit|blocked`；检测器行是 advisory 审计记录，永不决定 source/severity/verdict，不进 G6 manifest 与 L6 ledger。
- **recirculate map**（ui-evaluator SKILL.md 权威表）：observable → 声明工件（`spec`/`domain`/`craft`/`design`/`components`/`template`/`native-craft`/`reference`）；repair map（`references/repair.md`）：失效类 → owning declaration + 受影响证据；证据新鲜度规则（Fill 变化失效绑定证据、overwrite/revision 命名、引用被取代 artifact 出 warning 而非硬 Pass）。
- **a11y 附接规则**（`references/a11y-tree.md`，ADR-0016）：无障碍证明优先附到既有 user-risk L6；仅当无障碍失败是独立阻断的用户可见风险才单列 L6；不自动生成 a11y L6 种子。
- **上游 #28 产物**（评审的输入侧）：契约字段 `l6.c1…cN`（decided）、`export.*` 类假设字段（assumed + notes 含理由/风险/回退/来源链）；spec L1-L6（L6 = Given→When→Then + 必备证据 + capture seed）；成形会话工件（archived 后为 run 记录过程证据）；证伪信号以 finding 回流 D1 时走「重开子树」机制。

---

## 1. 评审维度：三轨维度清单（工单项 1）

评审对象是 **S6 之后的产物**：已实现界面（Fill 产物）对照已确认的声明（契约 + spec + 决策报告 + 基线）。三轨各自有维度清单与每维证据要求；每条 finding 必须声明所属轨。

### 1.1 产品轨（product track）——逐条 AC

- **职责**：判定实现是否支持已确认的验收判据。判据单位 = spec L6 顶层项（= 契约 `l6.cN`）。
- **判定枚举**（与 ledger `result` 一一映射，不造第二套值域）：

| 判定 | ledger result | 语义 | 判据 |
| --- | --- | --- | --- |
| 支持（supported） | `pass` | observed 证据满足 required proof（必备证据 + capture seed） | 证据存在、已绑定、且 evaluator 判定覆盖 Then 子句全部用户可见结果 |
| 不支持（unsupported） | `fail` | 证据存在但与 Then 矛盾（截图可以证伪判据） | 证据绑定完整 + observation 与 required 不符 |
| 无法验证（unverifiable） | `blocked` | 必备证据不可得（provider 缺席、状态不可达、capture 失败） | 不可得的 required proof 记 blocked，不跳过、不臆断 |
| 不适用（not applicable） | `n/a` | 判据经确认不适用于本 run 范围 | **必须附理由**——本模型自立的评审协议义务（无上游条文可引）；机器面按第 7 节冻结，无理由的 n/a 由评审协议面拒绝 |

- **每条 L6 恰一行 ledger**（G2 既有机器面，原样保留）。判定的机器可查部分（行存在、字段非空、值域、Pass 全 pass、artifact 绑定）归门禁；「observed 是否真的满足 required」归 evaluator——两分法与现状一致。
- **无对应契约的发现不在评审中现场发明产品要求**（#24 D4 既定）：评审只能引用已存在的 `l6.cN`/L1-L5/决策条目；发现落点无声明可指 → 回流 D1（见第 8 节路由 R1）。
- **assumed 可见性义务**（#28 接口）：finding 涉及 assumed 字段（如 `export.column_scope`）时必须引用其假设状态；依赖假设的 L6 判 pass 时 ledger `required` 行标注依赖。

### 1.2 交互轨（interaction track）——主路径走查

- **职责**：判定已实现界面的可用性事实——动作、状态、反馈、恢复、信息组织是否构成闭环。走查单位 = D2 交互模型的路径与节点（L3 链路 + #32 将落码的 L2-L5 结构化字段），不是逐像素巡览。
- **维度清单**（每维一行：可机器验证的客观面 + 需人工证据的主观面，严格分开）：

| 维度 | 客观面（可自动验证的复现事实） | 主观面（Q8：默认 advisory，须人工证据） |
| --- | --- | --- |
| 动作可发现性（discoverability） | 动作存在、可达、可聚焦（source/interaction 层） | 目标用户是否会注意到（需 user test / 认知走查人工记录） |
| 状态可解释性（system response & completion signal） | 状态出现、反馈存在、完成信号出现（rendered/interaction） | 反馈是否可理解、是否足够显著 |
| 错误可预防/可诊断/可恢复（error prevention, diagnosis, recovery） | 错误出口可执行、恢复路径存在、undo/exit 存在 | 错误信息是否真正可理解、恢复是否可完成 |
| 信息按任务组织（task-organized information） | 术语/命名与契约及 spec 的一致性（机械比对） | 信息层级与分组是否符合用户心智模型、术语适配 |
| 跨视图状态闭环（cross-view state closure） | 返回后状态保持、数据保留（确定性运行事实） | 跨视图记忆负担（元素计数不能证明认知负担） |
| 逐页五态完备（five-state completeness） | 每页初始/加载/成功/失败/空状态存在（含权限/超时变体） | 各态文案与呈现质量 |
| 路径闭环（path closure） | 主路径每步可执行、无死端（interaction 轨迹） | 路径是否是用户最重要的走法（重要性需产品确认） |

- **主观维度的处置**（Q8 落地）：认知负担、满意度、审美、术语适配、心智模型五类**只能产生 advisory finding**；finding 必须标注 `confidence: agent-judgment` 类来源；要成为阻断必须先经 D7 晋升（用户裁决）或项目显式声明——评审模型不提供任何晋升通道，只提供「呈报用户」的路由（见第 4.4 节）。
- 交互轨 finding 仍须回指 owning 声明（五态缺失→spec L5 深化字段；术语不一致→契约/spec；等），沿用「无指征不立项」禁令（禁止「整体还可以优化」类无回指发现）。

### 1.3 横切适用性矩阵（cross-cutting applicability matrix）

- **首版两项**（Q5=A）：
  - **无障碍（accessibility）**：以 a11y tree capture 为主证据；附接规则沿用 ADR-0016（优先附到既有 user-risk L6，独立阻断风险才单列）；name/role/state/keyboard path/focus/物质性遗漏是判断面。树的既有诚实边界保留：树的存在不证明视觉对比度、命中区尺寸、动效安全——这些缺口记 finding 而非臆断 pass。
  - **响应式（responsive）**：以 capture contract 声明的 viewport 组为准（manifest `request.viewport` 已是机器可查字段）；至少覆盖契约声明的目标视口；未声明目标视口本身是 finding（回流 D1/D2）。
- **占位三项**（国际化、性能感知、安全体验）：以 D7 注册表 advisory 占位规则存在，各带**显式适用谓词**（applicability predicate）。谓词求值三态：
  - `applicable` → 执行检查（advisory finding 输出）；
  - `not-applicable` → 记录理由（如「单语文档界面，无 i18n 声明」），不静默跳过；
  - `blocked` → 运行时证据不可得时记 blocked（如「性能感知需运行时度量，provider 缺席」），同样是显式记录。
- 横切 finding 的 severity 按用户可见后果定（与三轨同把尺子），**不因「横切」本身升降级**；无障碍硬约束（如键盘死端）达到 S3 事实类时照常 blocking。

---

## 2. 页面与流程覆盖模型（工单项 2）

覆盖是声明的函数，不是评审员的即兴抽样。覆盖单位来自 D2 交互模型（L2 页面职责表 + L3 路径表 + 逐页五态，#32 落码为结构化字段）。

### 2.1 覆盖等级

| 覆盖等级 | 范围 | 义务 |
| --- | --- | --- |
| **必审（exhaustive）** | 主路径（primary path）全部节点 + 必需低频路径（required rare paths）全部 + 逐页五态矩阵 | 无一例外走查；每个节点至少一条证据（层别不限，按维度证据要求） |
| **采样（sampled）** | 边缘情形（edge cases）、分支路径变体 | 按**五态×页面矩阵**采样（决议 Q3）：必审范围之外，每页×每声明五态至少一处证据，矩阵缺口可机械枚举；采样理由入报告 |
| **显式未审（declared-unreviewed）** | 采样后仍未覆盖的路径/状态/视口 | 列入覆盖声明；不得默认通过 |

### 2.2 逐页与跨页的职责切分

- **页内职责（per-page）**：逐页五态完备、页面职责与 L2 声明一致、页内控件语义（components 轨道既有检查）——证据以 rendered/source 层为主。
- **跨页流程（cross-page flow）**：路径闭环、跨视图状态保持、返回路径、决策点可达——证据必须含 interaction 层（静态截图证明不了流程）；measurement 层作印证。
- 判定归属：页内缺口 → 逐页维度 finding；跨页缺口 → 路径维度 finding；两者不可互相替代（页页都合格但流程断链是合法发现，反之亦然）。

### 2.3 覆盖缺口的报告义务

- 报告必含**覆盖声明（coverage statement）**块：必审清单的完成状态、采样清单与理由、显式未审清单。
- 「未审」不等于「通过」：显式未审项在 verdict 语义中不产生 pass 贡献；若未审项涉及主路径必审范围，覆盖声明本身记 `blocked` 级覆盖缺口（这是评审自身的失败，不是被评审物的失败——回流 evidence plan，见 R5）。
- 交互模型自身缺页（spec 没写某页面/状态）→ 不是覆盖缺口而是声明缺口 → 回流 D2/D1（R2/R1）。

---

## 3. 四层证据与方法语义（工单项 3）

### 3.1 四层定义与能力边界

| 层 | 内容 | 典型 artifact | 能证明 | 不能证明 |
| --- | --- | --- | --- | --- |
| **source（源码层）** | 代码引用（file:line、token、组件用法） | 源码定位（自由文本入 ledger note/finding，非 manifest artifact） | 存在性、结构事实、声明↔代码一致性、token 纪律 | 任何运行行为、任何用户可感知结果 |
| **rendered（渲染层）** | 静态产物：截图、a11y 树 | `evidence/L6.<n>-*.png`、a11y tree capture（manifest 绑定） | 特定 viewport 下可见状态、name/role/state、物质性遗漏 | 行为闭环、时序、真实用户是否注意/理解 |
| **interaction（交互层）** | 操作轨迹：动作序列 + 状态转移记录 | interaction trace capture（manifest 绑定） | 动作可达、状态转移确实发生、返回保持、错误出口可执行 | 可发现性（用户视角）、认知负担、满意度 |
| **measurement（测量层）** | 数值测量：耗时、计数、成功率 | 派生测量记录（trace 派生计数/计时，manifest 绑定） | 绑定具体用户/任务/环境下的量化事实 | 无上下文阈值的通用结论（响应时长/步骤数只有在绑定判据后才有意义） |

两分法（每层内部再切）：**存在性/一致性事实**可自动验证（绑定完整性、provenance、词表一致——G6 既有）；**含义与解释**归 evaluator 与人工证据。

### 3.2 证据层数与 AC 判定的最低要求

- 判 `unsupported`（fail）：至少一层证据 + observation 与 required 的矛盾点——任一层都可证伪（截图可以证明判据为假）。
- 判 `supported`（pass）：最低证据要求（决议 Q2）——**implemented UI 每条 L6 判 pass 必须至少一条绑定的 rendered 或 interaction artifact**（manifest 绑定，G6 可查）；source/measurement 单独不足以判 pass（源码存在不等于运行发生；测量印证但不独立成立）。**planning-only 工作豁免**（无 Fill 产物、无运行面）：pass 以声明覆盖证明，observed 可为自由文本，但报告不得宣称发生过渲染或测试。
- 判 `unverifiable`（blocked）：必备层不可得（如行为判据但 provider 缺席）。

### 3.3 方法语义（D5 五字段）与绑定层对接

每条**绑定到 criterion 的证据**（manifest 条目）由 orchestrator 在绑定时附方法语义——append-only 新增可选键，旧读取方忽略未知键，向后兼容：

```json
{"criterion": "L6.1", "capture": {...}, "artifact": "...", "observed_state": "...", "result": "captured", "ts": "...", "request": {...},
 "method": "runtime-observation",
 "observation": "选定 214 行触发行内导出，14.2s 后下载完成，CSV 214 行",
 "interpretation": "满足 c1 的 Then 子句（限时内完成且行数一致）",
 "scope": "单次运行，viewport 1280x800，Chromium，数据集 week-2026-32",
 "population": null, "ethics": null}
```

- `method` 枚举（对齐 #24 D5 + HCI 研究方法表）：`static-inspection | runtime-observation | expert-review | user-test | interview | survey | field-observation | telemetry | controlled-comparison`。
- `observation`（事实）与 `interpretation`（解释）**分离**：观察写测得/看到的，解释写它对 criterion 意味着什么；pass/fail 判断永远来自 evaluator 读两者，不来自 provider。
- `population` / `ethics`（同意/匿名化/保留期限）：**涉人证据（user-test/interview/survey/field-observation）必填**，缺失时该证据不可用于支持任何判定（记 blocked）；非涉人证据可空。
- `scope`：结论可推广范围与未控制变量——覆盖声明与限制声明直接引用此字段。
- 落点已定（决议 Q6）：**manifest 条目内新增可选键**——方法语义与 criterion 绑定同址，append-only、旧读取方忽略未知键，向后兼容；不另造工件、不动 ledger 机器面。
- **代理自身观察**（expert-review 类，含代理走查）必须在 `method` 显式声明，且其 finding 只能 advisory（Q8），除非被验证的是可复现事实——method 语义本身就是防「专家判断冒充用户证据」的机器可查字段。

---

## 4. 严重度与置信度（工单项 4）

### 4.1 severity：按用户可见后果分级（与 Q7 决策权表对齐）

现有值域 `high (blocking)|high|med|low` 的括注把「严重度」与「处置」耦合成一个字段。决议 Q1：**分轴**——severity 与处置是两个独立字段；旧字段写法保留为兼容别名，机械换算与迁移归 #32（后续修订：别名期已由 ADR-0028〔vNext S5〕终结——自 v0.20.0 起旧写法是结构错误 `G2.finding_invalid_severity`，不再静默折算；下表「向后兼容映射」列仅存迁移历史语义）：

| 级 | 名称 | 判据（后果） | 向后兼容映射 |
| --- | --- | --- | --- |
| **S3** | 阻断级后果（blocking-severity） | 破坏 L5/L6 声明、不安全/危险操作、数据丢失风险、主路径死端、键盘死端 | `high (blocking)` |
| **S2** | 重大（major） | 主路径受阻但有替代出口、横切硬约束命中、五态缺失但有兜底 | `high` |
| **S1** | 轻微（minor） | 工艺/一致性/文档缺口，无直接用户可见后果 | `med` / `low` |
| **S0** | 信息/正向（info / positive） | 正向发现、观察记录、无修复义务 | （新增，无现值） |

- 分级尺子是**任务/用户影响**而非措辞强度（D7 既定）；同一 finding 在不同任务语境下可不同级——severity 判定须引用受影响的 L6/主路径节点。
- S3 事实类（可复现、证据绑定完整）→ 处置 blocking，进 G4 closure；S3 判断类 → 见 4.4。

### 4.2 confidence：结论可信度的来源

confidence 描述「这条 finding 的证据基础有多硬」，由三个来源派生（决议 Q4：三级序数 `high | medium | low`，派生规则机器可查）：

| 来源 | high 的条件 | 降级条件 |
| --- | --- | --- |
| **证据层数** | 跨层印证（如 rendered + interaction） | 单层，尤其仅 source 层的行为类断言 |
| **复现性（reproducibility）** | 确定性重跑一致（机器 capture、机械比对） | 单次观察、时序敏感、代理一次性走查 |
| **判断主体** | 人工确认或机器可复现事实 | 代理判断（agent-judgment）、启发式命中 |

派生规则（决议 Q4，机器可查）：机器可复现事实且跨层 → high；机器可复现单层或人工确认 → medium；代理判断/启发式命中/单次观察 → low。

### 4.3 severity × confidence → 处置（disposition）

处置枚举：`blocking | advisory | info`。finding 新增字段行 `disposition:`（四字段保持不变，附加行被现有解析器忽略，向后兼容）。

| 组合 | 事实类 finding（可复现、绑定完整） | 判断类 finding（主观/语义/代表性） |
| --- | --- | --- |
| S3 | **blocking**（进 G4 closure） | **advisory + 呈报用户**（escalation，见 4.4） |
| S2 | advisory（进 point-back 修复清单，不阻 verdict） | advisory |
| S1 | advisory | advisory |
| S0 | info（正向发现，见第 5 节） | info |

- **判断类 S3 永不直接 blocking**（Q8）：启发式命中不得直接判阻断缺陷；模型给它的通道是「advisory + 呈报用户」——按 Q7 第 5 行，blocking 处置仅当改变声明或接受风险时用户介入，所以判断类发现的升级动作是请求用户裁决（改声明/接受风险/晋升规则），不是 evaluator 自行阻断。
- **判断类未命中不得判体验通过**：advisory 无发现 ≠ 该维度通过——限制声明兜底（第 6 节）。
- advisory finding 不进 G4 closure、不阻 Pass；但 S2 事实类 advisory 在 Recirculate 轮次中应随 owning 修复一并处理（修复建议可见性）。

### 4.4 呈报用户（escalation）通道（决议 Q5：进入首版）

判断类 S3（或用户可裁的任何 advisory）在报告的「待用户裁决」子块列出：发现 + 证据 + 建议动作三选一（修改声明 / 接受风险并记录 / 提交 D7 晋升队列）。该块是呈报协议，不制造第二 verdict；用户响应走既有决定机制（decisions.jsonl `supersedes` / D7 队列 / 契约字段修订）。此通道是判断类发现唯一的升级路径——没有它，判断类 S3 永远停留在 advisory，信号流失。

---

## 5. 正向发现（positive findings，工单项 5）

- **地位**：正向发现不是装饰性表扬，是「AC 被满足」的验收证据面——与 fail finding 同等进入证据结构，防止「只记录问题、通过部分无凭据」。
- **载体**：不另造工件。AC 的正向证据就是 ledger 行本身（`result: pass` + observed 证据引用 + 方法语义）；跨 AC 的模式级正向观察（如「五态在全部必审页面齐全」）以 S0/info finding 记录，仍须回指声明。
- **强制正向证据**（决议 Q2）：**implemented UI 的每条 L6 判 `pass` 必须有至少一条绑定的 rendered 或 interaction artifact**（manifest 绑定，G6 可查）；measurement/source 只作印证不作独立支持；自由文本 observed 仅 **planning-only 工作合法**（无 Fill 产物与运行面的 run，声明覆盖即为证明面，报告不得宣称发生过渲染或测试）。
- **无证据 ≠ 失败，= 无法验证**：判据缺证据时记 `blocked`（unverifiable），不记 `fail`——「没测」与「测了不行」是不同事实，混同会制造虚假 fail 或隐性通过。blocked 的判据照常阻 Pass（G3：Pass 需全 pass），其回流多为 evidence plan（R5）或 provider 缺席的运行面问题。
- **正向发现的限制**：pass 记录的 scope 受方法语义约束（单 viewport/单环境/单次运行的 pass 不可普遍化）；覆盖声明显式未审范围内的 AC 无正向证据义务（它们本就不该有判定）。

---

## 6. 验证边界（validation limits，工单项 6）

评审**不能宣称**的事项，以报告必含的**限制声明（limitations statement）**块显式化——防过度声明的机制不是免责套话，是机器可查的固定结构：

| # | 边界 | 限制声明中的表述义务 |
| --- | --- | --- |
| L1 | 主观维度结论 | 逐条列出判断类 advisory 的维度（认知负担/满意度/审美/术语适配/心智模型），标注「代理判断或启发式，非用户证据」 |
| L2 | 用户代表性结论 | 无 user-test 类证据时，报告不得出现任何「用户会/用户觉得/对用户而言」断言；涉人证据的 population/scope 必须引用 |
| L3 | 覆盖采样 | 「采样不等于穷尽」+ 显式未审清单引用；必审未完成记覆盖缺口而非通过 |
| L4 | 证据推广范围 | 每条 pass 的 scope 限定（单 viewport/环境/数据集）；不宣称跨环境有效 |
| L5 | 机器能力边界 | 「机器检查证明声明与事实一致，不证明体验良好」——结构完整性门禁的既有哲学升为报告固定语 |
| L6 | 代理角色边界 | 代理未替代用户确认；assumed 字段的 pass 依赖假设成立（逐条引用假设状态） |
| L7 | 弱证据叠加 | 多种弱证据相加不等于强结论（R-11 约束）；三角验证的结论须逐层证据各自 scope 内成立 |

- 限制声明的机器化已定（决议 Q7）：**Limitations 与 finding 附加字段首版纯协议消费**，机器化归 #32 视 D7 注册表落地节奏；覆盖声明另见第 7 节（进最小存在性门禁）。
- 边界不是评审的弱点而是产品承诺：verdict 的可信度以「它不说什么」定义。

---

## 7. 报告形态（report artifact，工单项 7）

报告工件仍是 `.scratch/<run>/point-back.md`（stage registry 固定名，不新增文件），从现有三段（ledger + findings + verdict）扩展为六块结构。**机器面字段一字不改**（四字段 finding、四字段 ledger 行、closure 行、verdict 语义全部保留），新块以无字段行或附加字段行进入——现有解析器（`ledger_syntax.parse_ledger` 跳过无字段块；`_findings` 忽略四字段外的行）天然容忍：

```text
## Evidence ledger          （既有，每 L6 恰一行；required 行可标注依赖假设；
                              observed 附加 note: 行引用方法语义摘要）
## Findings                 （既有四字段；新增附加字段行：track: product|interaction|cross-cutting
                              severity: S3|S2|S1|S0（决议 Q1 分轴；旧值写法为兼容别名）
                              confidence: high|medium|low（决议 Q4 派生规则）
                              disposition: blocking|advisory|info（Q1 分轴处置字段）
                              evidence: <artifact 路径或源码引用，多行可>
                              assumes: <涉及的 assumed 字段路径，有则必填>）
## Positive findings        （新增：S0/info 行 + 模式级正向观察；AC 级正向即 ledger pass 行，此处只汇总引用）
## Coverage statement       （新增：必审完成状态 / 采样与理由 / 显式未审清单 / 覆盖缺口；决议 Q7：进最小存在性门禁）
## Limitations statement    （新增：L1-L7 逐项适用者 + 待用户裁决子块[决议 Q5]；首版纯协议）
## Verdict                  （既有：恰一 Pass|Recirculate + closure 行，语义不变）
```

- 与现有 ui-evaluator 报告的关系是**延续而非替换**：G2/G3/G4/G6 消费的面完全不动；新增面按决议 Q7 分层——**Coverage statement 进最小存在性门禁**（必审完成状态 + 显式未审清单的存在性校验，不判内容），Limitations 与 finding 附加字段首版由协议消费（ui-evaluator 技能与 D4 评审走查），正式 schema 与剩余机器化归 #32 按本定稿落码。
- craft-guard 检测器行维持现状：`.scratch/<run>/craft-guard.md` 独立审计记录，advisory 输入，不进 ledger/manifest/verdict（#24-Q4 已定迁 D7 注册表，格式迁移归 #30）。
- 报告不出现分数/评分——「分数与清单是诊断，不是验收」（D4 既定）；severity/confidence 是结构化事实而非量化打分。

---

## 8. 回流路由（point-back recirculation，工单项 8）

### 8.1 两层路由：声明工件层（既有）→ 声明层（D6 五类）

现有 recirculate map 的 observable → 声明工件路由保留为第一跳（`spec`/`domain`/`craft`/`design`/`components`/`template`/`native-craft`/`reference`/seam）；本原型在其上加第二跳——声明工件 → D6 五类回流目标，并给出 finding 侧的路由判据（observable 特征 → 目标层）：

| 路由 | 目标层 | 触发特征（finding 判据） | 落点动作 |
| --- | --- | --- | --- |
| **R1** | requirement（D1 重开成形子树） | 发现无对应契约/spec 声明可指（「无主发现」）；判据不可判定（Given/When/Then 本身缺口）；assumed 字段被证伪；非目标边界争议 | 走 #28 证伪机制：失效子树重开新成形会话，`supersedes` 修订；**评审不现场发明产品要求** |
| **R2** | interaction model（D2 spec L2-L5 深化字段） | 五态缺失、路径断链、决策点/返回保持未建模、页面职责缺 | 补 spec 结构化字段（#32 schema）；受影响 L6 重评 |
| **R3** | design decision（D3 决策报告） | 方案假设失败、取舍未记录、视觉方向与基线冲突 | 补/修订 decision report（#31 schema）；预览重确认按 G5 |
| **R4** | implementation（Fill 实现） | 实现偏离已确认模型：动作缺失、状态错误、token 散落、组件误用 | 修实现，从消费该声明的步骤恢复；只修 owning 层 |
| **R5** | evidence plan（D5 证据计划） | 方法不能回答判据（capture seed 错配）、provider 缺席、样本/环境不匹配、证据不足而非实现错 | 修 capture plan / 换 provider / 补采证据；实现不动 |

- 多层复合发现（如「高危灰标签」）允许多 `source:` 值（现有格式已支持多值），第二跳取**最小 owning 集**；修复顺序按声明层依赖（R1→R2→R3→R4），evidence plan（R5）在任一层修复后都可能追加。
- **路由规则本身归机器**（D6 既定：observable→owning layer 映射可自动）；「修订后的声明是否真的解决根因」归人工判断。

### 8.2 失效证据集（invalidated evidence set）

repair map 的证据新鲜度规则升级为显式结构（Recirculate 时在 point-back.md 增列）：

```text
invalidated:
  - criterion: L6.2
    artifacts: [evidence/L6.2-error.png]
    reason: Fill 修复导出提示后 observed UI 变化
  - criterion: L6.1
    artifacts: []
    reason: 契约字段 export.column_scope 证伪，行数判据依赖该假设
```

- 失效范围可计算（最小集）：直接受影响 criterion + 以被证伪字段为来源链的派生 criterion（#28 2.4 失效集计算的下游对应物）；未受影响 criterion 的证据保留。
- 原失败证据与修订原因保留（append-only 哲学）：被取代 artifact 走 overwrite/revision 命名，最新 manifest 条目胜；ledger 引用被取代 artifact 出 warning（repair map 既有规则）。
- 重评只跑失效集 + 相邻主路径（D6 最小修复）；轮次预算两轮停止（机器计数归 #32）。

---

## 9. 走查示例：「数据导出入口」的实现评审（工单项 9）

沿用 #28 第 6 节同一例子：S6 已通过（D-0004 `l6.c1`、D-0005 `l6.c2` 已确认；`export.row_cap`=200000 等 4 个 assumed 已 ack）；本幕模拟 Fill 完成、observe* 采集后的 ui-evaluator 评审。日期 2026-08-14。

**输入**：spec L6（c1 限时导出/行数一致，证据=交互记录；c2 超限提示剩余量与收窄建议，证据=错误态截图 capture seed）+ 契约（c1/c2 decided；`export.column_scope` assumed「当前视图列含隐藏列开关」）；必审 = 主列表页→行内批量导出→下载完成主路径 + 导出错误态；采样 = 边缘（空选择导出、超时中断）；显式未审 = 移动端视口（契约未声明目标视口，已有 finding）。

### 9.1 产品轨判定（AC 三条演示）

```text
criterion: L6.1
required:  Given 运营在主列表选定上周范围 When 触发行内批量导出 Then 30 秒内获得 CSV 且行数与选中范围一致（证据：交互记录）
observed:  evidence/L6.1-export-trace.json 14.2s 完成，214/214 行；measurement 印证 evidence/L6.1-timing.txt
result:    pass
note:      method=runtime-observation; scope=单次运行, viewport 1280x800, 数据集 week-2026-32
```

（正向证据满足最低要求：绑定 interaction artifact；measurement 印证不独立成立。）

```text
criterion: L6.2
required:  Given 选定范围超过 20 万行 When 确认导出 Then 提示剩余量与收窄建议（证据：错误态截图 capture seed）
observed:  evidence/L6.2-cap-error.png 提示含「超出 200,000 行上限」与「按周导出」建议
result:    pass
note:      assumes=export.row_cap
```

（第二幕演示 c2 的横切发现，见 9.3；此处 pass 依赖 assumed 字段 `export.row_cap`——按可见性义务标注。）

```text
criterion: L6.3
required:  Given 导出进行中 When 用户离开并返回该页 Then 导出进度与结果仍可获知（证据：交互记录）
observed:  必备交互记录不可得：capture provider 在导出进行中导航场景下 session 丢失
result:    blocked
```

（「没测」≠「测了不行」：blocked 阻 Pass，回流 R5 evidence plan——capture 计划需支持跨导航采集；实现未判有罪。）

### 9.2 交互轨发现（两条：一客观一主观）

```text
issue:    导出进行中触发按钮无 busy/disabled 状态，可重复触发并发导出
source:   spec L4（导出控件状态转移）
fix:      导出进行中置 busy 并禁重复触发，完成后恢复；补 L4 状态行
severity: S2
track:    interaction
confidence: high
disposition: advisory
evidence:  evidence/L6.1-export-trace.json（轨迹显示 2 次连续触发）; src/Console/ExportButton.tsx:42
```

（状态可解释性维度；事实类（轨迹可复现）S2 → advisory，进修复清单不阻 verdict。）

```text
issue:    导出选项术语「定界符/编码」疑超出运营角色的任务语言，或增加无谓决策负担
source:   spec L1（目标用户）+ L4
fix:      将高级选项折叠为「高级」默认收起；术语适配待用户研究确认
severity: S2
track:    interaction
confidence: low
disposition: advisory
evidence:  rendered 走查（agent-judgment, method=expert-review）
```

（术语适配/认知负担是 Q8 主观维度：判断类、低置信、**永不 blocking**；S2 判断类 → advisory；「疑超出」「待确认」措辞即限制——代理不得断言用户真实负担。）

### 9.3 横切发现（一条）

```text
issue:    超限提示 toast 无可访问名称与 role=alert，屏幕阅读器用户无法感知导出失败原因
source:   spec L6.2（owning user-risk criterion，ADR-0016 附接）+ components
fix:      toast 增加 role=alert 与可读名称（含超限数值）；组件语义入 components 声明
severity: S3
track:    cross-cutting
confidence: high
disposition: blocking
evidence:  evidence/L6.2-a11y-tree.json（节点无名无 role）
```

（无障碍横切、事实类（a11y 树可复现缺失）、S3 → blocking，进 G4 closure；附接到既有 user-risk L6.2 而非新造 a11y 判据。占位三项本例均 `not-applicable`：单语控制台无 i18n 声明 / 性能感知需运行时度量记 blocked 一项入覆盖声明。）

### 9.4 severity × confidence 组合一览（本例）

| finding | severity | confidence | 类别 | 处置 |
| --- | --- | --- | --- | --- |
| a11y toast 无名无 role | S3 | high（机器可复现 + rendered 层） | 事实类 | **blocking**（G4 closure） |
| 导出按钮无 busy 态 | S2 | high（interaction + source 跨层） | 事实类 | advisory |
| 术语「定界符」适配 | S2 | low（agent-judgment 单层） | 判断类 | advisory（L1 限制声明引用） |
| L6.3 采集不可得 | —（覆盖缺口） | — | 评审自身 | blocked → R5 |
| L6.1 pass | S0 | high（跨层印证） | 正向 | info（正向证据） |

### 9.5 回流路由演示（各一例）

- **R4 implementation**：a11y toast blocking → 修 Fill 组件实现；失效集 = L6.2 的 rendered 证据（`invalidated:` 块登记 `L6.2-error.png`/`a11y-tree`，reason=Fill 修复后 UI 变化）；重评只跑 L6.2 + 主路径相邻节点。
- **R5 evidence plan**：L6.3 blocked → capture 计划补跨导航 session 策略；实现不动、契约不动。
- **R1 requirement（无主发现演示）**：走查中发现实现带「导出历史记录」入口，spec/契约无此声明——不现场发明产品要求，登记无主发现回流 D1，由成形会话裁决（补声明或确认移除实现）。
- **R2 interaction model（演示一例）**：空选择点导出无响应（采样发现）——L5 未建模该边缘态 → 补 spec L5 五态行，非实现 bug。

### 9.6 覆盖与限制声明（本例节选）

```text
## Coverage statement
必审: 主路径 4/4 节点完成; 导出错误态完成; L6.3 采集 blocked（覆盖缺口→R5）
采样: 边缘 2/2（空选择=发现R2; 超时中断=通过, 证据 evidence/edge-timeout.png, 理由=高频中断风险）
未审: 移动端视口（契约未声明目标视口→已立 finding 回流 D1/D2）
横切: a11y=applicable(1 finding); 响应式=blocked(视口未声明); i18n=not-applicable(单语); 性能感知=blocked(provider 缺度量面); 安全体验=not-applicable(无敏感操作新增)

## Limitations statement
- 判断类 advisory: 术语适配（agent-judgment, 非用户证据）
- 用户代表性: 本 run 无 user-test 证据, 全部结论不构成任何「用户会」断言
- pass 范围: L6.1/L6.2 pass 限单 viewport/单数据集/单次运行
- assumed 依赖: L6.2 pass 依赖 export.row_cap 假设成立
- 机器面证明声明↔事实一致, 不证明体验良好
```

**verdict**：`Recirculate`（1 blocking 未闭合 + 1 blocked 证据行）；closure 行待 R4 修复重评后按 G4 记录。

---

## 10. 对后续工单的接口

| 工单 | 本原型交出的接口 |
| --- | --- |
| #30 | 横切占位规则的适用谓词三态语义（applicable/not-applicable/blocked）；advisory detector 输出的 finding 附加字段格式（track/confidence/disposition）；判断类 S3 呈报通道的 D7 队列条目 |
| #31 | R3 路由的 finding 特征清单（方案假设失败/取舍未记录） |
| #32 | 六块报告结构与已定机器化范围（Q7：Coverage 进最小存在性门禁，Limitations/附加字段协议）；finding 附加字段行与 ledger note 行的正式 schema；manifest 方法语义新键（Q6）；失效证据集块 schema；R1-R5 路由映射表；旧 severity 值兼容别名的换算迁移（Q1）；D2 结构化字段（覆盖模型的输入）落码 |
| #33 | D4/D5 最小可交付集建议：三轨 finding schema + 方法语义五字段 + 覆盖声明 + R4/R5 路由（R1-R3 依赖 #28/#31/#32 产物成熟度） |

## 已确认决议（2026-08-14，用户裁决：全部按建议采纳）

| 题 | 问题 | 决议 |
| --- | --- | --- |
| Q1 | severity 与处置是否分轴 | **A：分轴**——severity 独立三级 S3/S2/S1（+S0 正向）按后果定级，处置独立字段 `blocking\|advisory\|info` 由 severity×类别×confidence 组合派生；旧字段写法保留为兼容别名，换算迁移归 #32 |
| Q2 | AC 判 pass 是否强制至少一条绑定 artifact | **A：implemented UI 强制**——每条 L6 判 pass 须至少一条绑定的 rendered 或 interaction artifact（manifest + G6 可查）；source/measurement 仅作印证；自由文本 observed 仅 planning-only 工作合法（声明覆盖为证明面，不得宣称发生过渲染或测试） |
| Q3 | 采样路径的最低覆盖要求 | **A：五态×页面矩阵采样**——必审之外，边缘情形按「每页×每声明五态至少一处证据」采样，矩阵缺口可机械枚举，其余显式未审 |
| Q4 | confidence 的表达方式 | **A：三级序数 + 机器派生规则**——`high\|medium\|low` 由三来源（证据层数/复现性/判断主体）按 4.2 节表派生，派生规则可查 |
| Q5 | 判断类 S3 的「待用户裁决」通道是否进首版 | **A：进入**——限制声明含「待用户裁决」子块，三选一动作（改声明/接受风险/提交 D7 晋升队列）；呈报协议不制造第二 verdict，用户响应走既有决定机制 |
| Q6 | 方法语义五字段的落点 | **A：manifest 条目内新增可选键**（method/observation/interpretation/scope/population+ethics）——append-only、旧读取方忽略未知键、与 criterion 绑定同址 |
| Q7 | 新报告块首版是否进机器门禁 | **A：Coverage 进最小门禁，Limitations 协议**——覆盖声明「必审完成状态 + 显式未审清单存在性」进 G 门禁（存在性校验不判内容）；Limitations 与 finding 附加字段首版纯协议消费，机器化归 #32 |
