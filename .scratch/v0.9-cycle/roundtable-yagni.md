# 圆桌表态 · YAGNI 怀疑者 · v0.9 范围

**Q1 发版切割 —— 攒,且这笔 runtime 变更发出去之前应先改。**
读了 mcp/evidence/server.py:146-159。触发条件是 `not configured or configured == "."`,而注释自陈仓库根 .mcp.json 出厂就是 RUN_ROOT=".";包内 .mcp.json 只声明 env_vars 不给默认值,外部安装者是 unset——两条路径命中同一分支。即:这条 WARNING 在默认安装、完全正确的用法下也会每次打到 stderr。它没有检出异常,是在对出厂默认配置报警。天平上多出来的不是 runtime 修复,是一个恒真告警。真正的静默 mis-root 是"cwd 不是预期 run 目录",当前判据无法区分,因为正确用法走同一分支。建议把触发收窄到 cwd 下无 run 标记(plan.md / point-back.md)时才警告,或每进程只打一次;改完再连同下一个实质改动一起发。以现状发布是用一次 publish 主动给每个新用户制造噪音——静默只坑用错的人,噪音坑所有人。

**Q2 repeat_blockers 断言化 —— 反对。**
20 runs / 0 blockers,断言 ==0 在恒真集合上永远绿,今天不保护任何东西。语义也错配:重复 blocker 出现时要的是"看见并去查",不是让 CI 变红拦住发版。断言化把发现信号误编码成回归信号,第一次真触发就会被当噪音 skip。保持报告。

**Q3 doctor 整合 aggregate —— 反对,对称癖。**
doctor 答"环境能不能跑",aggregate 答"历史跑过什么",消费者与时机都不同。零证据表明有人先跑 doctor 才想看聚合。唯一共同点是同在 scripts/ 下,那不是需求。

**Q4 下一主题 —— d) 收束,等外部信号。**
P1 template-zone:前置票 dedup-single-source issue 03 已 resolved,技术阻塞确实解除;但 ADR-0010 rule 3 的真判据是 "only when a shipped consumer exists — never parked speculatively",template-zone 零消费信号,判据未满足。攒 dogfood:已覆盖 export-jobs / api-keys / team-invite / hitl / multi-step-form / event-stream / settings / tarot 共 20+ runs,同质度高,repeat_blockers=0 正是边际发现递减的读数。当前最大未知不是缺哪个功能,而是包发到 npm 后有没有人用——3b community catalog 那个人工阻塞才该消耗人力。

**我最坚持的一点**:repeat_blockers 恒为 0 不是"该加门禁"的理由,而是"该停下来找外部用户"的信号;Q1 那条恒响的 warning 与它同病——继续自产自销地喂工具,只会让"给自己造工具"的偏差越陷越深。
