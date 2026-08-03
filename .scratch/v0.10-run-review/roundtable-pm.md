# 圆桌表态 — 产品负责人（v0.10 跨 run 复盘）

## 用户什么时刻会想跨 run 复盘

不是每次 run 结束后的仪式，而是**痛感触发**：同一类 blocker 第三次冒出来、阶段交付前想说清"我们老栽在哪"、或有人接手项目问"这套流程对我们有效吗"。所以入口必须能被用户**主动想起并叫出来**，不能藏在某个 skill 的第 5 节里。

**第一版最小到什么程度还有意义**：只要能回答一个问题——"哪些 blocker 在多个 run 里重复出现"——就有意义。一张重复项频次表 + 一张 per-run 结果表，够了。JSON 契约、趋势、评分都是后话。

## 01 落点 — 选 a + e：第四个 command 作入口，薄的新 skill 承载指引

command 是用户唯一会主动敲的表面，可发现性只能靠它。指引主体不进 `ui-evaluator`：那个 skill 的心智是"**一次** run 的验收"，塞进跨 run 统计会稀释它的契约。若最终指引不足 40 行，退而求其次接受纯 a（全写在 command 里）。反对 b（ui-review 加 scope 参数）——参数分叉是给已经懂的人用的，新用户看不出这里有能力。

## 02 输出契约 — markdown 表为主，JSON 不做第一版必需项

消费者是**人**，读的是复盘。镜像 aggregate 的 JSON 形状收益是我们内部的心智一致，不是用户的价值，且过早锁死对外 schema 会变成发版债。心智一致改用**字段同名**实现（run / result / repeat blocker），不靠结构。版本标记要，但轻：markdown 标题行带 `run-review/v1`，只承诺"这是这一版的表形状"，不承诺 JSON schema。

## 03 计算主体 — 逐 run 调 shipped `validate_run.py`，agent 只做归并

该脚本已随包发、用户手里就有，per-run 门禁结果确定性来自它；agent 手工判 Pass/Fail 必然失真。2–5 个 run 就是 2–5 次子进程，成本可接受。最少 run 数 **2**，不足直接拒绝并说明"跨 run 复盘至少需要 2 个 run"。归一化只写一条可复述规则进指引（大小写折叠 + 空白折叠，完全相同才算同一条）。漂移锁的方向：**内部脚本跟对外指引**，不是反过来——对外文案是契约，内部工具是实现。

## 04 对外词汇 — 对外叫 run review，`repeat blocker` 原样保留

能力名 `run review`（command/skill 名），文案里说"跨 run 复盘"。`repeat blocker` 保留：它是有定义的名词，用户需要它来指代那张表。`run aggregate` 不进对外文案——它绑定的是本仓脚本，用户没有 `.scratch/**/dogfood/`。禁止事项写成**集中的 Never 列表**（不建 run ledger / 不散文化 lessons / 不自动回流 baseline），放在 skill 末尾 Guard 段——`ui-evaluator` 已有 `## Guard` 先例；散在步骤里的边界会被跳读。

## 我最坚持的一点

第一版只回答"哪些 blocker 重复出现"，用 markdown 交付，**不引入 JSON 对外契约**——一旦发出去，形状就再也改不动了。
