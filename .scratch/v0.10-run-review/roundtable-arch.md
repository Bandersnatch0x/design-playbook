# 圆桌表态 — 架构师(v0.10 跨 run 复盘)

## 01 落点 → (e) 新独立 skill `run-review`,不新增 command

per-run 管线的边界是 `.scratch/<run>/` 单 run 契约,orchestrator 每步都写本 run 产物;跨 run 不是 run 的一步,加节撑破作用域。扩 `ui-evaluator` 更糟——它是本 run verdict 权威,塞进跨 run 频次等于让纯统计沾上判定权,直接违反域纪律。扩 `ui-review` command 会让一个入口有两种输出契约,反对。orchestrator 只在第 10 步 Done when 后加**一行 pointer**(注明"跨 run,非本 run 步骤"),discovery 靠 skill description。command 面 3→4 要连带改 plugin.json / README / gate 多处,v0.10 不值。

## 02 契约 → markdown 表为主 + JSON 可选;**要** `run-review/v1` 版本标记

包内已有 `design-baseline/v1` / `schema_version: 1` 先例,新对外产物无版本标记是负债。关键区分:**对齐键名,不承诺形状**。`runs_total` / `rollup.by_result` / `repeat_blockers` 三个顶层键名照抄(零成本心智一致),但不声明"镜像 aggregate_runs 的 JSON"——把未打包内部工具的形状写进对外契约是反向依赖,内部工具从此不能演进。

## 03 计算主体 → 混合;规则单源方向定死

- **gate 列**:逐 run 调 shipped `validate_run.py`(已在包内、零新增打包面、结果可复核)。子进程数 = run 数,可接受。
- **artifact 完整性**:agent 直接看文件在否,无失真空间。
- **repeat blocker**:agent 分组,规则一行——`observed` casefold + 折叠空白后**逐字相等**才同条,`result != pass` 才计入,count ≥ 2 才叫 repeat。
- **门槛**:< 2 run 直接拒绝。
- **run 发现规则须自写**:`aggregate_runs.py` 默认 glob `.scratch/**/dogfood/*` 是本仓形状,用户侧是 `.scratch/<run>/`,照抄会全空。

**漂移锁法(点名回答)**:不用"指引引用代码为准"——shipped 文案引用未打包脚本是反向依赖,用户也无从核对。方向反过来:**shipped 文案是 SSOT,`aggregate_runs.py` 是 follower**,与 `run_status.STAGES` 镜像 SKILL.md 的既有方向一致。落法:monorepo 加 `tests/test_normalize_lockstep.py`,用语料对(大小写/多空格/CJK/尾随空白)断言 `normalize` 仍满足文案声明的规则,并在 `normalize` 上加 sync 注释。锁的是**语义**不是字符串,与 `test_digest_lockstep` 同形。

反对"只做 rollup 不算 repeat blocker":repeat blocker 是跨 run 复盘唯一的新信息,砍掉就只剩 N 次 validate_run,不值一个 skill。

## 04 词汇 → 对外统一 **run review**;`repeat blocker` 原样保留

`run aggregate` 是内部 glossary 且绑着本仓 dogfood 扫描语义,对外误导。`repeat blocker` 自解释且是纪律术语,保留。禁止事项写成**集中 `禁止:` 块**(SKILL.md 第 4 步已有此形态),不散在步骤——它们是跨步骤不变量,散着写会在步骤重排时静默丢失。除三条既定禁止外补第四条:不得按语义聚类 `observed`,只准逐字分组——这是"不散文化学习"在计算层的落法。

另补 seam 提醒:被回填过的 manifest `observed_state` 会让跨 run 统计说谎。复盘只统计 `result` 与 gate 状态(结构诚实性由 G2/G3/G6 卡住),`observed` 文本仅作分组键,不得据以判断"证据强度"。

**我最坚持的一点**:归一化规则的 SSOT 必须是 shipped 文案、`aggregate_runs.py` 做 follower,并用语料 lockstep 锁住;反过来让对外指引指向未打包脚本,等于把内部工具变成对外契约。
