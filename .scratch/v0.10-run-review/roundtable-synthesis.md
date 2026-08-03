# 圆桌综合 — v0.10 跨 run 复盘

Label: roundtable:synthesis · 2026-08-03

## 1. 一览表

| 票 | 产品负责人 | 架构师 | YAGNI | DX |
| --- | --- | --- | --- | --- |
| 01 落点 | a+e，退可纯 a | e 新 skill，反对新 command | c 最小变体（references/） | a+e，退可纯 a |
| 02 契约 | markdown-only，轻版本标记 | markdown+可选 JSON，要版本标记 | markdown-only，**不要**版本标记 | markdown，对齐列名，留版本标记 |
| 03 计算 | 逐 run 调 validate_run | 混合＋lockstep 锁归一化 | **砍掉 repeat blocker** | 条件式 seam＋四条防失真 |
| 04 词汇 | run review，集中 Never | run review，集中禁止块＋第 4 条 | 不造新词 | run review，Never 绑进 Done when |

**核查**：doctor.py:30-31 `GATE1_EXPECTED_SKILLS=8`/`COMMANDS=3` **已核**；package.json `files` 仅 skills/commands/mcp/NOTICE **已核**（npm/pi 装不到 `scripts/`）；`design-baseline/v1` 版本标记先例 **已核**；`tests/test_digest_lockstep.py`、`test_stages_lockstep.py` **已核**；orchestrator 219 行、`ui-evaluator` `## Guard`（:108）、`SKILL.md:86` `**禁止:**` **已核**；YAGNI 实测 A **已核并复跑**（20 runs / 112 行 / `{pass:109, blocked:3}` / `repeat_blockers` 空）。

## 2. 逐票综合

### 01 落点 → 纯 (a)：新增一个 command，不新增 skill

**共识**：四人一致否决 (b) 扩 ui-review、(d) 扩 ui-evaluator。
**分歧**：可发现性（PM/DX）对维护位点（YAGNI/Arch）。
**裁决**：取 PM 与 DX 都主动写下的退让项——**纯 command 内联，约 40 行**。理由：跨 run 只能显式调用，藏进 references/ 等于没有入口，而入口正是本能力的全部价值；同时新 skill 的成本经 YAGNI 点破比 command 更高（gate 常量＋README＋`codex/AGENTS.md` 编排顺序），且会把一个不属于 pipeline 的东西塞进线性顺序——这恰是架构师自己的作用域论证所反对的。
**落地**：新建 `packages/design-playbook/commands/run-review.md`；`scripts/doctor.py:31` 常量 3→4；README 命令枚举三处；`docs/agents/release-checklist.md` 措辞改为"八 skills + 四 commands"；orchestrator 第 10 步 Done when 后加**一行 pointer**并注明"跨 run，非本 run 步骤"。**ui-evaluator 的 description 与 Steps 一字不动**（DX 最坚持项，全票不冲突）。

### 02 契约 → markdown 表为主，不发 JSON schema，保留 `run-review/v1`

**共识**：markdown 为主；v1 不承诺 JSON schema；与 aggregate_runs 只对齐**列名/键名**，不对齐结构。
**分歧**：版本标记，3 比 1。
**裁决**：保留。YAGNI 说它是对不存在用户的兼容承诺——但落在 markdown 抬头的一行字串不承诺任何可执行契约，只是给人读的溯源标签，且包内已有 `design-baseline/v1` 先例（已核）；成本一行，收益是日后改形状时可读。
**落地**：报告抬头 `run-review/v1`；逐 run 一行、**强制 run 路径列**；repeat blocker 段为纯频次表 `count | runs | 原始 observed 文本`，**不设"分析/建议"列**（DX：没有能写散文的格子，比一句 Never 管用）；point-back 用「路径 + `observed:` 逐字引用」，**不写行号**。

### 03 计算主体 → 保留 repeat blocker；条件式 seam；锁归一化

**共识**：gate 列必须来自 `validate_run.py` 的真实退出状态，禁止目测填；`observed` 仅作分组键，不得据以判"证据强度"。
**分歧一（最大）**：YAGNI 主张砍 repeat blocker，数据已核为真。
**裁决：保留。** 三点取舍：其一，PM 定义的 v1 唯一价值就是"哪些 blocker 重复出现"，砍掉后剩下的只是"跑 N 次 validate_run"，架构师说得对——那不值任何表面，届时该砍的是整个 v0.10 主题而非一半；其二，0/20 测的是**本仓 dogfood 语料**（`aggregate_runs.py` glob `.scratch/**/dogfood/*`），这些 run 被 gate 逼到完成故天然 ~97% pass，用户项目会中途弃置 run，样本不可外推；其三，YAGNI 的数据真正预言的失败模式是**没有 repeat 时 agent 编造 repeat 来填表**——所以把该发现写进指引，而不是删掉功能。
**分歧二**：漂移锁。**裁决**：采纳架构师方向（**shipped 文案是 SSOT，`aggregate_runs.py` 是 follower**，PM 明确同意），并落 `tests/test_normalize_lockstep.py`——monorepo 内、0 打包面、0 gate 常量，与已核的 `test_digest_lockstep`/`test_stages_lockstep` 同形。
**分歧三**：门槛。**裁决**：取 DX 版本——**含 `point-back.md` 的 run < 2 直接拒绝并报出 N**；无 point-back 的 run 上清单但贡献 0 行。
**落地**（写进 command 正文）：
- **条件式 seam**（DX 已核事实，压过 PM/YAGNI 的"已 ship 用户手里就有"）：`packages/design-playbook/scripts/validate_run.py` 仅 **plugin 安装态**存在，npm/pi 装不到。指引写成分支：能跑则逐 run 跑、判定 token 抄进 `gate` 列；跑不了填 `not checked`，**永不从"产物看着齐"推 ok**。
- 归一化**一行可复述规则**：`observed` casefold ＋折叠空白后**逐字符相等**才同条；`result != pass` 才计入；`count ≥ 2` 才叫 repeat。字面不同必须分列，至多加 `similar:` 指针行、**不合并计数**。
- **run 发现规则自写**：用户侧是 `.scratch/<run>/`，照抄 `dogfood/*` glob 会全空。
- DX 四条防失真全收：抽样截断先出清单表（`included / skipped+原因`，无行不得计数）；过度归一化禁止；manifest 回填诚实性提示（哈希对得上 ≠ 转录诚实）；rollup 数字必须逐行推出，禁"总体来看"。
- 新增一句（消化 YAGNI 实测）：**`_none_` 是正常结果**，本仓 20 个 run 实测 0 条 repeat；无重复时如实写 `_none_`，不得放宽归一化去凑重复项。

### 04 词汇 → 对外 `run review`；`repeat blocker` 原样保留

**共识**：能力名 `run review`，文案说"跨 run 复盘"；`run aggregate` 不外输（绑本仓脚本语义，用户会去找一个不存在的工具）。
**分歧**：`repeat blocker` 去留（YAGNI 的反对以砍功能为前提，功能保留则其自述理由自动消解）；Never 的位置，3 比 1 主张集中块。
**裁决**：`repeat blocker` 保留，首次出现处给一句定义（"normalized observed 跨 run 复现；只计数不判断"）。Never 取**集中 `禁止:` 块**（与已核的 `SKILL.md:86` 体例一致）——DX 的"末尾禁止段是背景色"论在 ~40 行的 command 里风险大幅下降；同时收 DX 的结构性兜底（无散文格子）与 Guard 一句 `counting, not judging`。
**落地**：禁止块四条——不新建 run ledger／不散文化 lessons／不自动回流 baseline／**不得按语义聚类 `observed`，只准逐字分组**（架构师补，是"不散文化学习"在计算层的落法）。ledger 行格式不复述，pointer 指向 `ui-evaluator` step 2。

## 3. 留给用户拍板的点

1. **是否保留 repeat blocker**（唯一实质分歧，且有已核反证数据）。**推荐保留**：砍掉后 v0.10 无新信息可交付；0/20 出自本仓 gate 语料，不可外推到用户项目。若您认同 YAGNI，正确动作不是砍一半，而是取消整个 v0.10 主题、只发 Fixed 段。
2. **command 面 3→4 是否值得**（YAGNI/Arch 反对新表面）。**推荐值得**：纯 command 只多 1 个 gate 常量＋README 枚举，避开新 skill 的 `codex/AGENTS.md` 顺序污染。
3. **`run-review/v1` 版本标记留否**。**推荐留**：一行字串、有 `design-baseline/v1` 先例。

## 4. to-spec 就绪判断

四票均可 resolve，无待查事实（关键主张已逐条核实）。**建议路径：跳过独立 spec，直接 implement。** 交付物只有一个新文件（`commands/run-review.md`，约 40 行）＋四处既有位点的枚举更新＋一个 monorepo 测试，形态与验收标准在本报告已具体到文件与行为，再写一份 spec 是把同一内容抄第二遍。实施顺序：command 正文 → doctor 常量与 README/release-checklist 同步 → `tests/test_normalize_lockstep.py`＋`normalize()` sync 注释 → orchestrator 一行 pointer → 跑 gate 与全量 pytest → 随 v0.10.0 与 Fixed 段（run-root WARNING 收窄、wait_for_state 指引）同发。
