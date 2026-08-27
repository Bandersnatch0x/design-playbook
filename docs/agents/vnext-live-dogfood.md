# vNext live dogfood checklist

Operational list for one **interactive** greenfield Design I/O run that proves vNext package surfaces before **0.12.0** release prep.

Companion script (preflight + post-verify):

```text
python scripts/vnext_live_dogfood.py preflight
python scripts/vnext_live_dogfood.py checklist
python scripts/vnext_live_dogfood.py verify --run-root .scratch/<run>
```

Prior surface probe (not a substitute for this list):
`.scratch/design-playbook-v0/dogfood/2026-08-08-vnext-surfaces.md`

## Fixed ask (default)

Use unless the user supplies another scene that is **not** tarot / settings / multi-step form:

> Build a greenfield **ops alert inbox**: table of alerts with severity, last seen, and one primary “ack” action. Empty / loading / error / no-permission must each have a next action. CJK labels ok.

Scene class: agent-ops list. Goal is process, not shipping the page.

## Preconditions (script: `preflight`)

- [ ] Repo on the vNext commits (validate + package scripts present)
- [ ] `python scripts/validate.py` → VALIDATION PASSED
- [ ] `python packages/design-playbook/scripts/doctor.py` runs (degraded without `DESIGN_PLAYBOOK_RUN_ROOT` is ok pre-run)
- [ ] Host can load plugin: `claude --plugin-dir <abs>/packages/design-playbook` **or** installed plugin (machine handshake: `python scripts/plugin_dir_smoke.py` from isolated config)
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
| 12 | Log | write dogfood md from template | — | six gates + artifact index filled |

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
- [ ] `run_status.py --json` returns stages + `next`
- [ ] `doctor.py --json --run-root <run>` not `broken`

Human:

- [ ] Process gates table complete (product-dogfood template)
- [ ] No Done-when skips without narration
- [ ] Blocking findings have recirculate trail or explicit acceptance
- [ ] Log saved under `.scratch/design-playbook-v0/dogfood/YYYY-MM-DD-HHMM-vnext-live.md`

## Log path

```text
.scratch/design-playbook-v0/dogfood/YYYY-MM-DD-HHMM-vnext-live.md
```

Use template: `.scratch/design-playbook-v0/dogfood/_template.md`.  
Add a short **vNext extras** section: bind/G7, capture schema, doctor level, adapters present/skipped.

## Exit criteria for “live dogfood done”

| Result | Meaning |
| --- | --- |
| **pass** | Full route attempted; machine verify green (or only accepted WARN); six gates filled; log written |
| **pass-with-skips** | preview* and/or observe* honestly skipped + enable path narrated; rest green |
| **fail** | Silent skip of Done-when, unversioned capture accepted, agent self-promoted `decided`, or verify red without known cause |

Only **pass** or **pass-with-skips** unblocks **0.12.0** release prep.
