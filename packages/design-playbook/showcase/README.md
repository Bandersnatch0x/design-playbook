# Showcase — cases and journey coverage

These **three independent historical tasks** demonstrate parts of evidence-backed UI delivery. They are not one current end-to-end run. Start with the [user journey](#user-journey), then open the source material for [Case A](#case-a), [Case B](#case-b), or [Case C](#case-c).

The current workflow is defined by the [orchestration contract](../skills/design-playbook/SKILL.md). Historical records retain their original scope, conclusions, and limitations; they do not establish current release readiness.

## User journey

| Your next question | Open the material | What is demonstrated here |
| --- | --- | --- |
| What does one complete current run look like? | [Case reader (live run)](case-reader/index.html) · [its run record](case-reader/run/point-back.md) | Current end-to-end run: real spec + preview confirmations, Fill, craft audit, captured evidence, six-block review, static handoff. |
| What must the UI do, and what counts as complete? | [Requirements and acceptance conditions](01-spec.md) | Case A: scope, permissions, edge states, and Given / When / Then criteria. |
| Can we agree on direction before implementation? | [Design decisions](02-decision-report.md) · [Human confirmation](04-preview-hitl.md) | Case A records decisions; Case B records human revisions and confirmation for a **different request**. |
| How do we identify and close a delivery gap? | [Findings and repair closure](03-point-back.md) | Case A: declaration-linked findings and the recorded repair / re-evaluation trail. |
| How does another engineer resume interrupted work? | [Status and continuation command](../commands/run-status.md) | **Command reference only**; no resume replay is packaged in these cases. |
| What can the team inspect at handoff and retrospective? | [Static handoff command](../commands/run-handoff.md) · [Cross-run review command](../commands/run-review.md) | **Command references only**; no generated handoff or cross-run review report is packaged here. |

## Case A

**Queue requirements, design decisions, and review closure.** The original SwarSight task asked: `在 SwarSight 加一个模拟运行队列监控页：看每个模拟任务的状态、失败重试、资源占用。`

1. [Specification](01-spec.md): six-layer requirements with permissions and acceptance criteria.
2. [Decision report](02-decision-report.md): structure and component choices before implementation.
3. [Point-back report](03-point-back.md): findings, repair closure, and the historical verdict. Its Positive findings and Limitations sections were later backfilled to the six-block report shape.

**Boundary:** this task predates ADR-0012. It does not package a design-baseline intake, reference intake, `plan.md`, preview confirmation, or captured `observe*` evidence. The report describes a single-viewport inspection with no involved-user evidence. Its recorded Pass is not a new evaluation of the current version.

## Case B

**Human confirmation of a form design.** The v0.4 dogfood 007 enterprise onboarding form is independent of Case A.

- [Four-round account](04-preview-hitl.md) and [review log](preview/log.md) explain the actual feedback and revisions.
- [Decision report](preview/decision-report.md), [first prototype](preview/round-1.html), [confirmed prototype](preview/round-4.html), and [confirmation record](preview/confirm-round-4.json) preserve the source artifacts.

**Boundary:** this demonstrates preview confirmation (G5), not acceptance of Case A's queue or of a production implementation. The selected prototypes are design artifacts; they do not run plugin commands.

## Case C

**Batch-retry confirmation implementation.** The v0.20.0 `retry-confirm` task is another independent request.

- Open [the queue interface](queue-monitor.html) locally alongside [its state module](queue-monitor-state.js) to inspect retry scope, error and empty states, and conservative defaults when reopening the dialog.
- [State-transition checks](test_queue_monitor_state.js) exercise the local interaction logic.

**Boundary:** this is a browser interface with **local mock data and no backend contract**. Clicking retry changes simulated queue state; it does not invoke design-playbook, execute a real job, or generate a run, evidence, or acceptance record. The historical task's complete run artifacts are not packaged beside this implementation.

## Current coverage gaps

The [case reader](case-reader/index.html) is one complete current run (spec → preview confirmation → Fill → craft audit → captured evidence → review → static handoff); its [point-back record](case-reader/run/point-back.md) is a single-agent declaration-driven review, not an independent expert audit. A second complete run (an ADR decision index, run locally under `.scratch/`) plus the cross-run review closed the retrospective gap: see [run-review 2026-09-08](run-review-2026-09-08.md) (2 runs with `point-back.md`, 0 repeat blockers, 0 rule-candidate qualifications). Command documentation in the journey table explains available entrypoints, not completed case evidence. Run Console remains local, experimental, and trial-gated.

Keep missing or unverified steps explicit; do not borrow a confirmation or Pass from these historical tasks.

To start a new case, follow the [installation instructions](../../../README.md) and current orchestration contract in the target project, then retain that run's actual outputs. This index does not supply missing historical artifacts or claim a new run has occurred.

## Historical illustrations

The `00-install` through `04-gates` images are **illustrated summaries rendered from curated HTML**, not raw browser captures of an executed workflow. Their archived labels and counts describe the old presentation, not the current package inventory. The six items in `04-gates` are the historical case checklist, **not the current G1–G6 gate matrix**.

| Material | Archived illustration |
| --- | --- |
| Installation summary | [00-install](screenshots/00-install.png) |
| Case A specification | [01-spec](screenshots/01-spec.png) |
| Case A design decisions | [02-decision-report](screenshots/02-decision-report.png) |
| Case A review and repair | [03-point-back](screenshots/03-point-back.png) |
| Case A historical checklist | [04-gates](screenshots/04-gates.png) |

## Maintainer checks

[Run validation tests](../tests/test_validate_run.py) exercise these declaration / report fixtures directly and separately check the preview confirmation directory. A passing structural regression does not turn the independent cases into one observed run or establish runtime UI quality. G6 coverage lives in the test fixture matrix and local dogfood records, not in a captured-evidence case packaged here.

From the repository root:

```text
python scripts/check_doc_links.py
python packages/design-playbook/tests/test_validate_run.py
node packages/design-playbook/showcase/test_queue_monitor_state.js
python packages/design-playbook/showcase/case-reader/selfcheck.py
```

The [case-reader self-check](case-reader/selfcheck.py) verifies the embedded delivery copy: every inlined document must equal its source bytes and sha256, the inlined `DOCS` literal must match `_gen_docs.js`, and the structural claims (error view, search input, noscript notice, no external network API, no external script tags) must hold. It needs only the Python standard library — no browser, Node, or package install — and paths resolve from the script location, so it runs from any working directory. Expected output on success: `OK: 4 embedded docs byte-identical, sha verified, structure checks pass` (exit 0).

To render updated **illustrations**, run `node scripts/screenshot-showcase.mjs` with `DPB_PLAYWRIGHT_PKG` and `DPB_CHROMIUM` as described in its header. Output goes to `.scratch/showcase-screenshots/`; archived images stay untouched. Rendering does not rerun or re-evaluate any case.
