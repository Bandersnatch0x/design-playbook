# 圆桌表态 · 发布工程 · v0.9 范围

**Q1 发版切割:攒,不发;且发布前必须先收窄那条 run-root WARNING。**
未发布的可分发面只有两处:evidence/server.py 的 RUN_ROOT stderr 诊断、SKILL.md 一句 wait_for_state 指引。两者都不新增可调用面(不改 tool schema、不改返回契约、不改 artifact 落盘位置),semver 上是 patch,不是 minor。但 patch 收益接近零,成本是 7 位点 + npm publish + 人肉五步 gate(含隔离会话 install smoke),不划算。
加上新事实后结论更硬:该 WARNING 在出厂默认(根 .mcp.json 发的 RUN_ROOT="."、外部安装则 unset)下恒触发,且 _run_root() 每次 capture 都调用一次 → 逐 capture 重刷。这不是"诊断改进",是给每个正常用户的 stderr 灌噪音,会训练用户忽略告警。现在发 = 把噪音发给所有人。必须先收窄(只在解析结果落在 run 目录外时告警,或每进程只发一次),修完再跟下个主题一起走 v0.10.0。现在强发 v0.10.0 是最差选项:没有 minor 素材却烧掉一个 minor 号,以后真有契约变更时没有信号强度可用。

**Q2 repeat_blockers 断言化:放 release.py,不放 validate.py。**
validate.py 每次 CI 跑且依赖 .scratch dogfood 产物;一次 dogfood 新增 blocker 会让所有无关提交的 CI 变红,把"产品质量信号"错接到"提交门"上。CI 红的语义必须是"这次提交弄坏了东西"。release.py 是人为触发的发版门,天然就是该盘点的时刻,repeat blocker ≥1 在那里 block 才对得上语义。validate.py 保持现状:它已经在打 repeat_blockers=N 的 info 行,可见但不阻塞。

**Q3 doctor 纳入 aggregate:不纳入。**
release-checklist 已明确"一条规则不得分叉成两处阈值/两处措辞"。doctor 已镜像 version 三点比对和 bundled-MCP,再镜像 aggregate 只加大漂移面,还让只读诊断变慢(要跑 17 个 run 的 validate_run.py)。对 release checklist 无正面影响。真要加,只加一行调用打 info,不加判定。

**Q4 下一主题与发版节奏:判据是 npm tarball diff,不是 main 上攒了多少提交。**
aggregate_runs.py、doctor.py 这类 repo-root 工具无论做多大都不进 tarball,用户拿不到,不构成发版理由。能构成 v0.10.0 最小包的只有改 skill 契约或新增 MCP 能力那一类候选;现有两处 pending 小改动(WARNING 收窄后)顺路搭车进 release notes 的 Fixed 段。

**Finding:release 流程缺"同步 phase.md 头部"一步。**
同一文件两处打架:phase.md:3 的 **Current:** 仍写 "v0.8.0 released",而 phase.md:32 表格行已记 v0.9.0 done;提交 6db8bc7 只改了 1 行,改的是表格那处。release.py 与 release-checklist.md 对 phase 的 grep 均零命中。根因是 phase.md 有两个"我们在哪"的写入点,发版流程只覆盖了一个。建议在 checklist 的 "Version + tag + publish" 段末补一条 checkbox(更新头部的版本 / tag / Release URL / npm latest)。不建议在 release.py 里断言成 block:phase.md 属 .scratch 内部记录,且现状是发布完成后才回填,发版当时断言方向是反的;最多加 warning 级提示。

**我最坚持的一点**:发版触发条件是 npm tarball 内容变化,而不是 main 上有提交;而这次 tarball 里唯一的行为变更(恒触发的 WARNING)本身就还没准备好出厂。
