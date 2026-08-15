# Filled UI — 队列监控升级（全局模拟运行中心第一步）

Fill 产物（round-2 修订触发 Re-Fill：preview round 2 修订决策报告后重走 Fill——W12 既有语义）。静态合成 dogfood：本文件为 Fill 面的声明性产物索引，不改 showcase 源文件。

## 实现面（按 decision-report 顶块 + spec 语义）

- 全局运行控制台 region：
  - 汇总计数（running / paused / failed）；
  - 运行 feed（≤12 条）：条目级进度、完成态含结果入口、失败项保留；
  - 全局暂停/恢复按钮：`role=button` + 可访问名称「全局暂停所有进行中模拟」（R4 修复后）；busy 态禁重复。
- 主列表区：运行表格（状态/场景/触发人/耗时/资源占用/操作）+ 失败条目圈选批量重试（操作条并入控制台，选中后浮现）。
- 侧区：失败趋势、队列压力、最近失败原因。
- 边界：无运行时 feed 不渲染；viewer 角色禁用全局控制并说明；暂停失败 toast（role=alert）。

## 声明对齐

- spec L4/L5 逐项实现；L6 判据证据绑定见 `evidence/manifest.jsonl`。
- sim.control_scope 假设生效：全局暂停不作用于手动单次重试（L6.2 轨迹核验）。
