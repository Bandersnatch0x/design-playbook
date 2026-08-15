# Dogfood — S6 P3 全量档（本仓库自身 UI 面）

S6 dogfood fixture（vNext 切片 6，工单 #41）：对本仓库自己的 showcase UI 面——SwarSight
模拟运行队列监控页（[`../../showcase/01-spec.md`](../../showcase/01-spec.md) 的运行面）——
跑一次 **P3 全量档全链**的静态工件集。

- 场景：把队列监控页升级为「全局模拟运行中心」第一步——修订既有 decided `l1.goal`
  （supersedes）+ region 构成变更（顶栏计数 → 全局运行控制台），命中 E 档判据 2 → P3。
- 全链义务：spec 契约投影（成形会话 S0-S6 + G9）、run-profile P3、E 档 DD 条目两轮
  preview 确认（G5/G10）、R3 重入（DD supersedes）+ 一条 R4 回流、方法语义证据
  （manifest 五键）、注册表适用谓词全目录求值（G8 run 级，13 行）、五态×页面采样矩阵
  完整执行（G11 S6 面：P3 档矩阵块强制）、六块报告 + invalidated 失效集、verdict Pass。
- 性质：**静态合成**（synthesized walkthrough）——工件的证据/哈希/事务记录为演示值，
  不依赖 chromium 与任何 provider 运行时；机器面由 `validate_run.py` 全量消费
  （见 `tests/test_vnext_s6.py` 的 dogfood 走查）。

## 走查要点（LR0-LR10）

| 环节 | 工件 | 门禁 |
| --- | --- | --- |
| LR1 定档 | `run/plan.md` run-profile 块（tier P3） | — |
| LR2 成形 | `run/shaping/shaping-log.jsonl` + `queue.json`；投影 D-0008..D-0011 | G9 + G1 + G7 |
| LR3 决策 | `run/decision-report.md` DD-0001（E 档，后被 R3 挑战）/ DD-0002（supersedes 修订） | G10 |
| LR4 预览 | `run/preview/` 两轮 decision/confirm 事务（round-1 选 B；round-2 修订后再确认 B2） | G5 |
| LR5 实现 | `run/filled-ui.md`（round-2 修订触发 Re-Fill） | — |
| LR6 工艺 | `run/craft-guard.md`（注册表 13 条全求值） | G8 run 级 |
| LR7 证据 | `run/evidence/manifest.jsonl`（方法语义五键；首轮失效证据 r2 重采） | G6 |
| LR8 评审 | `run/point-back.md` 六块 + 采样矩阵 10/10 全采样 | G2/G11 |
| LR9 回流 | R3（dd: DD-0001 → DD-0002 supersedes）+ R4（暂停按钮可访问名）→ 失效集重评 | 轮次/G4 |
| LR10 终局 | verdict Pass；基线漂移三出口「保持」复核 | G3/G12 |

## 校验命令

```bash
python packages/design-playbook/scripts/validate_run.py \
  packages/design-playbook/examples/dogfood/run/spec.md \
  packages/design-playbook/examples/dogfood/run/point-back.md \
  --preview-dir  packages/design-playbook/examples/dogfood/run/preview \
  --decision-report packages/design-playbook/examples/dogfood/run/decision-report.md \
  --evidence-dir packages/design-playbook/examples/dogfood/run/evidence \
  --run-root     packages/design-playbook/examples/dogfood/run \
  --contract-project packages/design-playbook/examples/dogfood/project \
  --contract-run packages/design-playbook/examples/dogfood/run \
  --shaping-dir  packages/design-playbook/examples/dogfood/run/shaping \
  --strict
```
