# 交互式自用验收手册

用于一次真实交互式 Design I/O run 的自用检查。它验证产品表面和交付证据，
不证明外部使用者采纳，也不满足外部试验门。历史脚本名中的 `vnext` 仅为兼容入口。

Companion script (preflight + post-verify):

```text
python scripts/vnext_live_dogfood.py preflight
python scripts/vnext_live_dogfood.py checklist
python scripts/vnext_live_dogfood.py verify --run-root .scratch/<run>
```

## 场景

优先采用真实自用任务；没有合适任务时，下例只能作为演练，记录中须明确标记为合成场景：

> Build a greenfield **ops alert inbox**: table of alerts with severity, last seen, and one primary “ack” action. Empty / loading / error / no-permission must each have a next action. CJK labels ok.

Greenfield 演练不计入既有 Web 产品的外部验证。已有产品任务按实际情况执行 baseline/reference，
不要为匹配下表的示例而跳过必要阶段。

## Preconditions (script: `preflight`)

- [ ] 记录源码 commit 或包版本，所需校验与产品脚本可用
- [ ] `python scripts/validate.py` → VALIDATION PASSED
- [ ] `python packages/design-playbook/scripts/doctor.py` runs (degraded without `DESIGN_PLAYBOOK_RUN_ROOT` is ok pre-run)
- [ ] Host can load plugin: `claude --plugin-dir <abs>/packages/design-playbook` **or** installed plugin (machine handshake: `python scripts/plugin_dir_smoke.py` — creates its own isolated config)
- [ ] MCP `tools/list` shows `preview_prototype` and/or `execute_capture_plan` (note which)
- [ ] If observe* will run: Playwright + Chromium installed

## Live route (script: `checklist`)

Copy this order; mark pauses when the agent stops for you.

| # | Step | Agent action | You (human) | Pass signal |
| --- | --- | --- | --- | --- |
| 0 | Entry | `/design-playbook:design-io <ask>` | confirm greenfield | baseline/reference skipped with one-line reason |
| 1 | Contract? | If project has `contract.json`, **bind-first** first | ack `assumed`; decide or leave `open` | bind blockers explicit; no silent decided |
| 2 | Spec | `ux-spec` → L1–L6 | answer L1 pause if asked | L5 not one-word; L6 = user-risk Given/When/Then (soft 3–7) |
| 3 | Plan | write `plan.md` three blocks | — | plan on disk before decision report |
| 4 | Decision | `ui-picker` report | one answer if platform unclear | decision-report before Fill code |
| 5 | preview* | only if adapter present | HITL confirm/revise | `confirm-round-*.json` with `confirmed` + `floor_pass` |
| 6 | Mid-run status | — | `python …/run_status.py <run> --json` | stages + next match reality |
| 7 | Fill | implement main flow + L5 paths | — | no copy from preview/reference assets |
| 8 | Craft | `craft-guard` rows | — | enabled detectors; N/A has reason |
| 9 | observe* | only if adapter present | set `DESIGN_PLAYBOOK_RUN_ROOT` to run abs path | each capture has `schemaVersion: 1` + viewport + freeze; manifest append per capture |
| 10 | Accept | `ui-evaluator` + verdict | Recirculate → smallest fix if blocking | point-back ledger; run artifact index shown |
| 11 | Machine seam | — | run `verify` (below) | exit 0 or known accepted warnings only |
| 12 | Log | record actual results and artifact index | — | process checks, limitations and unrun items explicit |

Skip narration required when preview* or observe* absent:

```text
-> preview*: adapter absent, skipped (G5 not triggered; enable via mcp/preview/)
-> observe*: adapter absent, skipped (G6 not triggered; enable via mcp/evidence/ + Playwright)
```

## Capture contract v1 (observe* only)

Every `execute_capture_plan` call must include at least:

```json
{
  "schemaVersion": 1,
  "viewport": {
    "width": 1280,
    "height": 800,
    "devicePixelRatio": 1,
    "colorScheme": "light"
  },
  "url": "<live or file URL>",
  "type": "screenshot",
  "state": "<label>",
  "actions": [],
  "artifact_path": "evidence/<name>.png"
}
```

Manifest line must embed the provider `request` (or equivalent schemaVersion + viewport). Unversioned evidence is invalid — recapture, no dual-read.

## Post-run verify (script: `verify --run-root …`)

Automated:

- [ ] Required files: `spec.md`, `plan.md`, `decision-report.md`, `point-back.md`
- [ ] `validate_run.py` text → RUN OK or documented INVALID
- [ ] `validate_run.py --format json` parses; errors have `rule_id` / `owner` / `repair`
- [ ] If `preview/` exists → G5 path via `--preview-dir` (+ `--decision-report` when present)
- [ ] If ledger cites `evidence/` → G6 via `--evidence-dir` / `--run-root`; capture schemaVersion=1 on bound rows
- [ ] If `contract.json` + bind snapshot → G7 via `--contract-project` / `--contract-run`
- [ ] If `craft-guard.md` in run root → G8 run-level registry (auto-engaged via `--run-root`)
- [ ] If `shaping/` under run root → G9 shaping exit (auto-engaged via `--run-root`)
- [ ] `run_status.py --json` returns stages + `next`
- [ ] `doctor.py --json --run-root <run>` not `broken`

Human:

- [ ] 记录下表的过程检查，使用自己的记录格式即可
- [ ] No Done-when skips without narration
- [ ] Blocking findings have recirculate trail or explicit acceptance
- [ ] 原始日志保存在本地忽略目录，不提交 Git

## 记录与人工检查

```text
.scratch/<run>/dogfood.md
```

无需私人模板。每项记录 pass / fail / skipped、证据路径与原因：

| 检查 | 必须记录的事实 |
| --- | --- |
| 声明 | 范围与 Criteria 是否覆盖真实风险和状态 |
| 决策 | decision report 是否先于实现，人工确认是否有据可查 |
| 实现 | 主流程及适用的空、加载、错误、无权限状态是否实际完成 |
| 证据 | Criteria 与 Artifact 是否绑定，缺失 adapter 是否如实披露 |
| 回流 | 阻塞 Findings 的 owner、修复与复验轨迹 |
| 交付 | 实际 verdict、工件索引、未跑项和剩余限制 |

另记运行日期、版本、场景来源、人工干预、bind/G7、capture schema、doctor 等级及 adapter 情况。
日志路径仅为示例，不要求其他维护者采用相同个人目录结构。

## Exit criteria for “live dogfood done”

| Result | Meaning |
| --- | --- |
| **pass** | Full route attempted; machine verify green (or only accepted WARN); six process gates filled; log written |
| **pass-with-skips** | preview* and/or observe* honestly skipped + enable path narrated; rest green |
| **fail** | Silent skip of Done-when, unversioned capture accepted, agent self-promoted `decided`, or verify red without known cause |

只有 **pass** 或 **pass-with-skips** 能作为该次自用检查的完成记录；
它不单独授权发布、catalog 提交或招募，发布还须遵守[发布清单](release-checklist.md)。
