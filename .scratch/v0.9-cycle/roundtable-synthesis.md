# 圆桌决策报告 · v0.9 范围 · 综合者

**总结论**:四问中 Q2、Q3 已达成全员共识(都是"不做");Q1 与 Q4 有实质分歧,我分别裁决为"先修 WARNING、不单独发 v0.9.1"和"主题转向把跨 run 复盘能力回流进包"。另有两个必须处理的仓内缺陷(phase.md 头部陈旧、WARNING 恒触发)。

## 1. 一览表

| | 产品负责人 | 架构师 | YAGNI 怀疑者 | 发布工程 |
| --- | --- | --- | --- | --- |
| Q1 发版切割 | 修 WARNING 后发 v0.9.1 | 按现状发 v0.9.1 | 攒,且发前必须先改 | 攒,发前必须先收窄 |
| Q2 断言化 | 现在不升级,判据应是"有决策条目"而非归零 | 不断言,且绝不落 validate.py | 反对,报告不该变门禁 | 要做也放 release.py,不放 validate.py |
| Q3 doctor×aggregate | 保持独立,只读引用不吞并 | 独立,两者读两个世界 | 反对,属对称癖 | 不纳入,最多加一行 info |
| Q4 下一主题 | aggregate 能力回流进包 | 攒 dogfood 频次基线 | 收束,转推 3b community catalog | 判据是 npm tarball diff |

## 2. 逐问综合

### Q1 发版切割

**共识**:四人一致认为未发布的两处改动(evidence WARNING、SKILL.md 的 `wait_for_state` 指引)在 semver 上都是 patch,不构成 minor;四人也一致认为这条 WARNING 按现状不能出厂。**分歧**在修完之后:产品负责人与架构师主张随即发 v0.9.1,YAGNI 怀疑者与发布工程主张攒到下个实质主题。

**推荐决议:先修 WARNING,但不为它单独发 v0.9.1,攒到下个主题一起走。** 取发布工程与 YAGNI 怀疑者,理由是发布工程给出的成本是具体的(7 个版本位点、npm publish、人肉五步 gate 含隔离会话 install smoke),而主张立即发的一方,其核心收益论据是"让外部安装者看见静默 mis-root"——这个收益在 WARNING 收窄成只在真 mis-root 时触发之后,恰好退化为"目前无人报告 mis-root",不具紧迫性。架构师"现状即可发"的立场基于 WARNING 有实际价值,但它在出厂默认下 100% 假阳性,这一点其余三人核实一致,应予推翻。设一条 tripwire:一旦收到真实 mis-root 报告,立即以 v0.9.1 补发。

**落地动作**:改 `packages/design-playbook/mcp/evidence/server.py:145-159`,把触发条件从 `not configured or configured == "."` 收窄为"解析出的 root 下无 run 标记(如 `plan.md` / `point-back.md`)",并加进程级 once 标志,消除逐 capture 重刷。

### Q2 repeat_blockers 断言化

**共识**:四人全部反对现在断言化。理由收敛于同一点——当前 20 runs / repeat_blockers=0,`==0` 在恒真集合上永远绿,保护不了任何东西,反而在首次真触发时被当噪音跳过。**分歧**仅在"将来若做,落在哪":架构师主张独立命令 `aggregate_runs.py --fail-on-repeat`,发布工程主张 `release.py`,产品负责人主张改判据本身,YAGNI 怀疑者主张永不。

**推荐决议:现在不做,并明确两条约束。** 第一,入场券是"至少观测到一次 `repeat_blockers > 0` 并完成闭环"(产品负责人),在此之前一切断言化提案不予受理。第二,届时判据取产品负责人的"每个 repeat blocker 有对应决策条目",不取 `==0`——后者会让如实记录重复阻塞变成受罚行为,与回流机制的激励方向相悖。落点取发布工程的 `release.py`(人为触发的发版门,天然是盘点时刻)。**绝不落 `validate.py`**,这是架构师与发布工程的共同底线,理由充分:门禁输入必须是本次 commit 可决定的东西,引入 `.scratch` 历史语料后 CI 会因无关 dogfood 变红,失去可复现性。`validate.py` 保持现状的 `repeat_blockers=N` info 行。

### Q3 aggregate 与 doctor 的关系

**共识**:四人一致——不合并。论据高度重合:`doctor.py` 的七项检查全部是安装态健康,对象是可分发表面;`aggregate` 读的是本仓 `.scratch` 历史语料,而安装用户根本没有 `.scratch`。二者共用"只读"这一性质不构成合并理由。**分歧**只有发布工程留了个"真要加就只加一行 info 调用,不加判定"的余地。

**推荐决议:完全不动,连 info 行也不加。** 采纳 YAGNI 怀疑者的判断——零证据表明有人先跑 doctor 才想看聚合;发布工程自己也指出加一行会让只读诊断变慢(需跑 17 个 run 的 `validate_run.py`)并扩大漂移面,那条余地不值得用。

**落地动作**:在 `CONTEXT.md` 记一句职责边界(doctor = 安装态健康 / aggregate = 跨 run 历史语料),避免此问被反复重提。

### Q4 v0.9 之后的下一主题

**分歧**最大的一问。产品负责人主张把 aggregate 能力回流进包内;架构师主张继续攒 dogfood 频次基线;YAGNI 怀疑者主张收束、转推 3b community catalog 那个人工阻塞;发布工程不选主题,而是给出判据——只有改 skill 契约或新增 MCP 能力那一类候选才进 tarball、才构成发版理由。

**推荐决议:主线取产品负责人的"跨 run 复盘能力回流进包",副线并行推 3b community catalog。** 理由是产品负责人的方案同时满足另外两人的约束:它改的是 skill 面,满足发布工程的 tarball diff 判据;它是给用户的能力而非给自己的工具,回应了 YAGNI 怀疑者"停止自产自销"的批评。架构师的"攒 dogfood"予以否决,因为其自身论据(语料不够密)已被两组数据驳倒:109 pass / 3 blocked 的平台期,以及 20+ runs 覆盖题材同质度高——`repeat_blockers=0` 更应读作边际发现递减,而非样本不足。

**落地动作**:起步范围压到最小,即一段 skill 指引 + 跨 run 输出格式约定,不搬 `aggregate_runs.py` 实现。同时把 **template-zone 从候选中摘掉**——三位角色独立核实一致:`zone` 在全部 dogfood 记录中命中 0 次,ADR-0010 rule 3 要求 "only when a shipped consumer exists",判据未满足。launcher 同理继续 defer。

## 3. 附带 findings

**F1 · phase.md 头部陈旧,且 release 流程缺一步。** 已核实 `.scratch/design-playbook-v0/phase.md:3` 的 **Current:** 仍写 "v0.8.0 released",而同文件表格行已记 v0.9.0 done。根因是该文件有两个"我们在哪"的写入点,发版流程只覆盖了表格那处,`release.py` 与 `release-checklist.md` 对 phase 的 grep 均零命中。**处置**:立即把头部改写为 v0.9.0 的事实(tag、GitHub Release URL、npm latest=0.9.0);在 `release-checklist.md` 的 "Version + tag + publish" 段末补一条 checkbox。采纳发布工程的判断,**不**在 `release.py` 中断言成 block——phase.md 头部是发布完成后才回填,发版当时断言方向是反的,最多 warning 级。提交时注意 phase.md 虽被 `.scratch` 整体 ignore 但已追踪,需用 `commit -a`,勿用 `add -A`。

**F2 · WARNING 恒触发是缺陷,不是诊断。** 处置见 Q1 落地动作。补充一条产品负责人的观察值得写进修复说明:`written_path` 返回绝对路径,本就是给 orchestrator 看见 misconfig 的精确信号,这条 stderr WARNING 与之冗余——收窄后若发现二者完全重叠,应直接删除而非保留。

**F3 · 关于修复形态的次级分歧。** 产品负责人认为"若默认值对外部安装者真的错,该修的是默认值而不是给自己的默认值加告警",与其余三人的"收窄触发条件"是两条不同路线。我推荐收窄触发条件、保留 `RUN_ROOT="."` 默认:改默认值会改变已发布 0.9.0 用户的 artifact 落盘位置,那是行为破坏,代价远大于当前问题。

## 4. 留给用户拍板的点

1. **是否单独发 v0.9.1。** 推荐:不发。先在 main 上修 WARNING,攒到下个主题一起走;若收到真实 mis-root 报告则立即补发 patch。(取发布工程 + YAGNI,弃产品负责人 + 架构师)
2. **下一主题选哪个。** 推荐:主线做"跨 run 复盘能力回流进包"(最小起步 = skill 指引 + 输出格式约定),副线并行推 3b community catalog 的人工阻塞;攒 dogfood 降级为顺带,template-zone 从候选摘除。(取产品负责人 + YAGNI,弃架构师)
3. **WARNING 修复形态。** 推荐:收窄触发判据 + 每进程只发一次,保留现有默认值;不改默认值以免破坏 0.9.0 已安装用户的落盘位置。(弃产品负责人的改默认值方案)

Q2 与 Q3 无需用户拍板——四角色立场一致,按上述决议执行即可。
