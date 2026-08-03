# roundtable-dx — DX / skill 文案工程（v0.10）

## 01 落点 → 新 command `/design-playbook:run-review` + 极小新 skill（a+e）

跨 run 只能靠**显式调用**。**否决 d**：把跨 run 写进 ui-evaluator 的 description，会在单 run 评审中途触发，agent 漂到兄弟 `.scratch/` 目录。否决 c：orchestrator 已 219 行/10 步，全挂在一条线性 `→` 数据流上，跨 run 不在链上任何位置，agent 会问"这步什么时候做"。否决 b：ui-review 委派 ui-evaluator，其契约是"每条 issue point back 到 declaration"，跨 run 只计数、无 declaration 可指，一 command 两语义＝agent 猜。只允许一件产物时退到 command 内联正文（约 40 行，装得下）。

## 02 输出契约 → markdown 表为主，不发 JSON schema

JSON 比 markdown**更**招编造：`runs_total`/`by_result` 让 agent 心安理得填合理整数。改逐 run 一行、**强制 run 路径列**。point-back 用「文件路径 + `observed:` 原文逐字引用」，**不要行号**——行号最易猜且不稳，路径+原文可 grep 自证。版本标记只留头部一行 `run-review/v1`；与 aggregate_runs 只对齐**列名**，不对齐 schema。repeat blocker 段 = 纯频次表 `count | runs | 原始 observed 文本`，**不设"分析/建议"列**：没有能写散文的格子，比一句 Never 管用。

## 03 计算主体 → 条件式 seam ＋ 四条防失真

**关键事实**：`packages/design-playbook/package.json` 的 `files` 只含 skills/commands/mcp，**npm/pi 安装态没有 `scripts/validate_run.py`**（仅 plugin 安装态有）。指引必须写成条件分支，不能假设 shipped：能跑就逐 run 跑、判定 token 抄进 `gate` 列；跑不了写 `not checked`，**永不从"产物看着齐"推 ok**。多子进程之虑被这条盖过。

1. **抽样截断**：glob 到 11 个只读 3 个却按 11 个报 rollup → 先出清单表（每个发现目录一行，`included / skipped+原因`），无行不得计数。
2. **过度归一化**（最伤）：把 "focus ring missing" 与 "no focus ring" 并成 count=2 → 只允许**逐字符**归一（小写＋空白折叠），字面不同必须分列，最多加 `similar:` 指针行、不合并计数。这句把规则钉在与 `normalize()` 同一定义上，无需搬码。
3. **manifest 诚实性传染**：被回填的 run 贡献干净 pass 行 → 同 gate 列，并注明哈希对得上 ≠ 转录诚实。
4. **就近概括**：细读最新一条就下总论 → rollup 数字必须逐行推出，禁"总体来看"。

门槛：<2 个含 `point-back.md` 的 run 直接拒绝并报出 N；无 point-back 的 run 上清单但贡献 0 行——不写明，agent 会把"缺"当 pass。

## 04 词汇 → 对外 `run review`，`repeat blocker` 原样

`run aggregate` 是脚本实现名，露出会让用户去找一个不存在的工具；用户动作是复盘 → **run review**。`repeat blocker` 保留原文，首次出现处给一句定义（"normalized observed 跨 run 复现；只计数不判断"），别逼用户读 CONTEXT，也别造中英两套词。

Never **不要独立成段**——长 skill 末尾的禁止段在 agent 眼里是背景色。绑进对应步骤的 **Done when**（负向条件同样可判定）：不新建 run ledger → *Done when:* `.scratch/` 下未新增跨 run 持久索引文件；不散文化 lessons → 表结构兜底 + *Done when:* 该段只有表行；不自动回流 baseline → *Done when:* 未编辑任何 `DESIGN.md`/`spec.md`/baseline state。Guard 段只留一句"counting, not judging"（与 ui-evaluator Guard 体例一致）。ledger 行格式不复述，pointer 指向 `ui-evaluator` step 2。

**我最坚持的一点**：ui-evaluator 的 description 与 Steps 一个字都不能改——那是唯一会污染单 run 触发的改动，代价远大于任何落点的便利。
