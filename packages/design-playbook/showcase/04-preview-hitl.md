# 04 · preview* HITL 演示（源自 dogfood 007，非主案例 ask）

> **来源声明（honest framing）：** 本节的 preview\* confirm + round 产物**不是**上方主案例（SwarSight 模拟运行队列监控页）的产物，而是取自 **v0.4 dogfood 007「企业入驻多步表单」**（`.scratch/design-playbook-v0/dogfood/2026-07-20-007-multi-step-form/`）的真实 HITL 运行。它单独演示 `preview*` 步骤（G5）如何在一个**不同 ask** 的产品 UI 上收敛——补 showcase 此前"声明存在但未证明 HITL 可收敛"的缺口（01 决策 1a/1b）。主案例（01–03）仍是 G1–G4 的单一深案例；`observe*` evidence 暂留 dogfood 日志，未进 showcase（体积 + 漂移负担，待稳定 fixture 化）。

## preview* 是什么

`ui-picker` 决策报告出炉后、进入 Fill 前，编排器探测 MCP `preview_prototype`；若 adapter 在场，生成一次性结构语义原型 HTML，弹窗由**人**确认/修改（HITL），adapter 落盘 confirm json（ADR-0008 feedback floor：非空 feedback 或 ≥1 anchor 触发，且每个 anchor 有非空 selector+comment）。G5 要求一份 `confirmed=true` **且** `floor_pass=true` 的 confirm，其 `report_ref` 指向当前 decision report。

## 本演示的 4 轮 HITL 轨迹（人审，非 mock）

| round | 决定 | feedback / anchor | floor | 说明 |
| --- | --- | --- | --- | --- |
| 1 | 需要修改 | `安师大安师大是`（无 anchor） | pass | ADR-0008 语义垃圾串——结构 floor 放行（非空触发），零可执行信号；语义判定属 evaluator，非 floor |
| 2 | 需要修改 | `[select #s] 需要修改字体` | pass | 真实 anchor（新证据）→ round-3 修 select/option 字体继承 |
| 3 | 需要修改 | `[#c] 改为一行两个` | pass | 真实 anchor（新证据）→ round-4 改 step1 两列行 |
| 4 | **确认通过** | 2 carry-forward anchor（按钮位置、手机 label 同行） | pass | `confirmed=true + floor_pass=true` → **G5 满足** |

完整轨迹见 [`log.md`](preview/log.md)；确认记录见 [`confirm-round-4.json`](preview/confirm-round-4.json)；精选原型见 [`round-1.html`](preview/round-1.html)（round-1 revise 原型）与 [`round-4.html`](preview/round-4.html)（被确认的原型）；决策报告见 [`decision-report.md`](preview/decision-report.md)。

## 关键契约在真人 HITL 下的实证

- **floor = 结构，semantic = evaluator**：round-1 真人喂语义垃圾，floor 结构性放行；编排器不臆造迎合性改动，按 decision report 自洽收紧结构。ADR-0008 分层在真人环成立。
- **capture≠judge 的对照**：confirm json 只记录"人确认了 + floor 过"，不判 UI 好坏；UI 验收是后续 ui-evaluator 的事（见 007 point-back）。
- **G5 非更高级 prompting**：是 adapter 写的机器可检记录（confirmed + floor_pass + report_ref 匹配），下方命令证明。

## 机器可检（G5）

```bash
python packages/design-playbook/scripts/validate_run.py \
  packages/design-playbook/showcase/01-spec.md \
  packages/design-playbook/showcase/03-point-back.md \
  --preview-dir packages/design-playbook/showcase/preview \
  --decision-report packages/design-playbook/showcase/preview/decision-report.md
# → RUN OK（G1–G4 沿用主案例 spec/point-back；G5 校验 preview/confirm-round-4.json）
```

`tests/test_validate_run.py` 的 `showcase/preview-g5` 用例直接跑此校验。
