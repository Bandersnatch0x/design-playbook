> Promoted from `.scratch/run-review-2026-09-08.md` (agent scratch is not distributed). The reviewed runs live where they ran: run 1 is packaged below in `case-reader/`; run 2 (ADR decision index) ran locally under `.scratch/adr-index-run/` and is not part of the distributed package — its findings are reflected in this report only. Paths below are as recorded at review time.

# run-review/v1 — showcase complete live runs (2026-09-08)

## 1. Inclusion manifest

| path | status |
| --- | --- |
| `.scratch/case-reader-run/` (junction → `packages/design-playbook/showcase/case-reader/run/`) | included |
| `.scratch/adr-index-run/` | included |
| `.scratch/craft-detectors/`, `design-playbook-closed-loop/`, `design-playbook-v0/`, `design-playbook-vnext/`, `dsh-lockstep-release/`, `elevate-structure-install-skills/`, `orphan-verdict/`, `preview-decision-transaction/` | skipped — no `point-back.md` (product-workflow phase dirs, not Design I/O runs) |

runs-with-point-back = 2 (≥ 2, review proceeds).

## 2. Per-run table

| run-path | ask | tier | preview confirm | ledger pass | blocking findings (history) | gate (validate_run.py exit) |
| --- | --- | --- | --- | --- | --- | --- |
| `.scratch/case-reader-run/` | 案例阅读器（完整实跑 #1） | P2 | shaping r1 + design r1, confirmed | 5/5 pass | 1 (S3, closed: error-view display) | 0 (warnings: 1 superseded-artifact) |
| `.scratch/adr-index-run/` | ADR 决策索引页（完整实跑 #2） | P2 | shaping r1 + design r3 (r1/r2 timeout-aborted, honestly recorded), confirmed | 5/5 pass | 1 (S3, closed: link depth) | 0 (warnings: 4 superseded-artifact) |

Gate commands run with `--require-preview --require-evidence`; both exited 0.

## 3. Repeat blockers

| count | runs | observed text |
| --- | --- | --- |
| _none_ | | |

Ledger rows `result != pass`: 0 in both runs. No repeat blockers exist; normalization was not loosened to manufacture any.

## 4. Rule candidate queue (derived view, protocol vNext S5)

| candidate id | runs | contexts | occurrences |
| --- | --- | --- | --- |

(none qualifies — distinct runs 2 < 3)

Below-threshold signals:

| normalized issue head | runs | gap list |
| --- | --- | --- |
| 初版 showError 使用 style.display='' 回退到 CSS 类 display:none… | 1 | distinct_runs 1 < 3 |
| 初版行链接使用三级上溯（../../../docs/adr/）… | 1 | distinct_runs 1 < 3 |

Context note: both runs' task contexts are readable from their `contract.json` / `spec.md` / manifest method-semantics keys (agent-driven dogfood runs on this repo, file:// offline read-only pages, Chinese-language UI). Both S3 findings were fact-class, evidence-bound, closed within their run; no unexplained false positives. The two S3 findings are not textually similar enough to merge under char-for-char equality (different surfaces: display fallback vs relative-path depth), and were **not** merged.

## 5. Point-back cites

- `.scratch/case-reader-run/point-back.md` — observed (L6.3): `evidence/L6.3-unknown-fragment-v2.png`
- `.scratch/adr-index-run/point-back.md` — observed (L6.3): `evidence/L6.3-invalid-fragment.png`

## 6. Rollup

Rows derived row-by-row: 2/2 runs included; 2/2 gate exit 0; 2/2 preview-confirmed (user, real Preview transactions); 10/10 ledger rows pass; 0 repeat blockers; 0 rule-candidate qualifications (2 signals below distinct-runs threshold). Junction note: `case-reader-run` is a filesystem junction to the showcase copy — same artifacts, one physical location; hash match is identity, not a transcription claim.
