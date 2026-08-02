# 圆桌表态 · 架构师 · v0.9 范围

**先纠一处背景事实**:`v0.9.0` tag 已存在,版本号 5 处已是 0.9.0。未发布包内容不止 SKILL.md 一句 —— `git diff v0.9.0..HEAD` 显示还有 `packages/design-playbook/mcp/evidence/server.py` `_run_root()` 的行为变更(RUN_ROOT 未设或为 `.` 时打 stderr WARNING)。这是 runtime,不是文案。

**Q1 → 发 v0.9.1 patch。**
两处改动都不动契约表面:`tools/list` schema、返回字段 `{artifact, observed_state, result, error, written_path}` 全未变,只多一条 stderr 诊断 + 一句 skill 指引。minor 应保留给契约新增。而 root `.mcp.json` 本身发的就是 `RUN_ROOT="."`,这条 WARNING 对外部安装者有实际价值(mis-root 现在静默),不该攒。`aggregate_runs.py` 在 repo-root `scripts/`,非发布面,不参与版本语义。

**Q2 → 不断言,且断言不该落在 validate.py。**
两层越界:(1) 语义 —— CONTEXT 定义 repeat blocker 为纯统计不下判断,`==0` 就是判断;(2) seam —— validate.py 是**静态结构门**,输入是仓内结构;引入 `.scratch` 历史语料后,gate 结果会随语料漂移:新 dogfood 撞一次归一化文本就红,与本次 commit 无关,CI 失去可复现性。真要断言,应是 `aggregate_runs.py --fail-on-repeat` 独立命令、人显式调用。判据也未达:当前 repeat_blockers=0 = 零误报证据,归一化质量未被真实 repeat 检验过。

**Q3 → 独立,doctor 不吞并。**
doctor 现有七检查(layout / gate1 smoke / versions / mcp / codex manifest / launchers / floor self-check)全部是**安装态健康**,对象是可分发表面。aggregate 读的是本仓历史 run 语料——安装用户根本没有 `.scratch`,并入后对他们只产生噪声 WARN,doctor 的"装了能不能用"语义被稀释。二者读的是两个不同的世界,共用只读性质不构成合并理由。

**Q4 → a) 攒 dogfood 频次基线。**
template-zone 的复出判据写得很硬(需真实消费 zone 的 L6),现在没有,重启就是自造需求;launcher 自 v0.5 defer 至今无新证据。20 runs / 0 repeat 说明语料还不够密,先攒到 repeat 真出现——那才是 Q2 断言化的唯一入场券。

**我最坚持的一点**:validate.py 不得依赖 `.scratch` 历史语料下断言——门禁的输入必须是本次改动可决定的东西,否则 gate 就不再是 gate。

> 注:此表态发出时更正尚未送达,但其自行核实了 v0.9.0 已发布这一事实,Q1 结论已基于正确前提。
