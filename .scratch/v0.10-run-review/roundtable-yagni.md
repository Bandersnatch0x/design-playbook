# 圆桌表态 — YAGNI 怀疑者（v0.10 跨 run 复盘）

Label: roundtable:yagni

## 先摆两组实测（本仓，2026-08-02）

**A. repeat blocker 从未命中。** `python scripts/aggregate_runs.py --md` 跑自家 20 个 dogfood run：112 条 ledger 行 → `by_result = {pass: 109, blocked: 3}`，3 条非 pass 的 normalized `observed` 互不相同（最高频次 1），`repeat_blockers` 输出 `_none_`。原因是结构性的：gate 逼着 run 完成前把 blocker 解掉，所以 ledger 天然 ~97% pass，repeat blocker 缺输入不是样本不够。

**B. 新表面的维护位点。** `scripts/doctor.py:30-31` 硬编码 `GATE1_EXPECTED_SKILLS = 8` / `GATE1_EXPECTED_COMMANDS = 3`。加 command = 改该常量 + README 第 57/75/119 三行 + 新文件 ≈ 5 处；加 skill = 常量 + README 技能表 + `codex/AGENTS.md` 编排顺序 + 新目录，而且它会挤进一条它根本不属于的 pipeline 顺序。references/ 下加文件则**不触任何 gate**（`install_skills.py:61` 是 glob，不硬编码）。

## 01 落点 — 选 (c) 的最小变体

orchestrator skill 加 `references/run-review.md` + SKILL.md 一行 pointer。1 个新文件、0 个 gate 常量、0 处 README 枚举。反对 (a) 新 command：`/help` 上多一格的收益要拿 5 处位点长期换。反对 (d) ui-evaluator：那是 per-run 评估、每 run 都加载，塞跨 run 散文等于给每次 run 上税。

## 02 契约 — 整票砍到"只有 markdown 表"

第一版不要 JSON，不要 `run-review/v1` 版本标记。插件没有已知外部用户（community catalog 未提交），版本标记是对不存在的用户许下的兼容承诺。不对称性决定方向：以后补 JSON 是加法、不破坏任何人；已发布的契约要收回是破坏性的。真需要 JSON 的人手里有 aggregate_runs.py 的形状可抄。

## 03 计算主体 — 第一版不做 repeat blocker

按实测 A，把 repeat blocker 移出 v1。顺带整票消解了本票最难的一半：没有 normalize 规则要跨两处同步，就没有漂移可锁。剩下 per-run rollup 表，计算主体用**已 ship 的 seam**：逐 run 调 `packages/design-playbook/scripts/validate_run.py` 并如实转录退出状态，禁止目测填 gate 列（哈希匹配≠转录诚实，同类失真已有前科）。最少 run 数不设硬门槛——没有代码可执行拒绝，指引里写"≥2 才有跨 run 意义"即可。

## 04 对外词汇 — 不造新词

不把 `run aggregate` / `repeat blocker` 这两个内部 glossary 原样外输；砍掉 repeat blocker 后第二个词自动消失。文案直接说"回顾过去的 run"，标题用平白语。三条禁止事项写成显式 Never 块（不新建 run ledger、不散文化 lessons、不自动回流 baseline）——各一行，比散在步骤里更省读者注意力，也符合 writing-great-skills 的明确约束偏好。

## 我最坚持的一点

砍掉 v1 的 repeat blocker。20 个 run、112 行 ledger、命中 0 次——给一个自家从未触发过一次的信号写对外指引，是 YAGNI 的字面定义；而且它一走，03 票的归一化漂移难题跟着一起走。
