# 圆桌表态 · 产品负责人 · v0.9 范围

前提:v0.9.0 已发布(2026-07-31,npm latest=0.9.0),版本位点已是 0.9.0。

## Q1 发版切割:发 v0.9.1 patch,但 run-root WARNING 不能按现状发

核实 `packages/design-playbook/mcp/evidence/server.py`:代码注释自己写明 root `.mcp.json`
**出厂即发** `DESIGN_PLAYBOOK_RUN_ROOT="."`(server.py:149),而 `_run_root()` 由每次
`_resolve_artifact_path()` 调用 → 逐 capture 重复。即:我们发一份配置,再警告我们自己发的配置。
出厂路径上 100% 假阳性。

这推翻了我原先"静默失败伤外部安装者、应尽快发"的论据。它没有区分"真的 mis-root"和"默认值",
只是把默认标记为可疑;发出去等于每个新装用户首跑就吃到重复 stderr,像缺陷,并训练用户无视告警。
且 mis-root 本已有精确信号——`written_path` 返回绝对路径,正是为让 orchestrator 看见 misconfig
(server.py:6-7、112-116)。WARNING 与之冗余。

产品结论:若默认对外部安装者真的错,**该修的是默认值,不是给自己的默认值加告警**。
- 首选:先修——判据改为"解析出的 root 不像 run 目录",且每进程只发一次,随 v0.9.1 一起发;
- 次选:若短期修不动,v0.9.1 只发 SKILL.md 那句 `wait_for_state` 指引,WARNING 押后。
两条路都是 patch:纯修复语义,无新能力、无契约变更,不构成 minor。`validate.py` gate 非发布面。

## Q2 repeat_blockers 断言:现在不升级

20 runs / repeat=0 此刻断言必然绿,那是样本没覆盖到,不是系统健康。判据应为:至少观测到一次
`repeat_blockers > 0` 并完成闭环之后。否则上线的是从未验证过失败路径的 gate。
更要紧的是激励方向——`==0` 会让如实记录重复阻塞变成受罚行为,与回流机制相悖。
真正该断言的是每个 repeat_blocker 有对应决策条目,而非必须为零。

## Q3 doctor 与 aggregate:保持独立,只读引用不吞并

aggregate 看跨 run 历史,doctor 诊断当前仓库健康,时间尺度不同。吞并会让 doctor 变慢、职责漂移,
且两者皆非发布面,合并对插件用户零收益。

## Q4 下一主题:把 aggregate 能力回流进包内

已查证 `zone` 在全部 dogfood 记录中命中 0 次(skills 内仅 5 处零散引用)→ template-zone 的 defer
判据不成立,应继续 defer 并从候选摘掉,直到有真实需求;launcher 三触发同样未满足;
堆 dogfood 已到 109 pass / 3 blocked 平台期,边际收益递减。
aggregate 现在只服务我们自己,v0.9 的价值全部滞留仓库内。让插件用户能对自己的多次 run 做跨 run
复盘(先从一段 skill 指引 + 输出格式约定起步),才是有产品面的下一主题。

## 我最坚持的一点

版本号是对用户的承诺,不是对我们工作量的记账;同理,告警是对用户的信号,不是对我们实现的注解——
出厂默认恒触发的告警,是把我们的配置债转嫁给用户。
