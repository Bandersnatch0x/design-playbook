# Automated operator acceptance

The required test inventory is [CI](../../.github/workflows/ci.yml). Quick
validate/link/doctor checks are necessary but do not replace its Python and
Chromium matrix. Complete acceptance requires that matrix to be green.
Missing Chromium is a failed gate, not an accepted skip.

## Extra-project replay

With the CI dependencies and Chromium installed, run from the repository root:

```sh
python -m pytest tests/test_operator_continuation_e2e.py -v --basetemp=.scratch/operator-replay --junitxml=.scratch/operator-replay-results.xml
```

`--basetemp` is disposable: pytest replaces that directory on a rerun. Do not
point it at a real project or a run you want to keep. On Windows use `python`
if the `python3` launcher is unavailable. CI runs the same test as a required
five-minute Chromium step and uploads the disposable project, JUnit result,
screenshots, and handoff archive for seven days.

The test copies [the inbox fixture](../../tests/fixtures/operator-project/spec.md)
into an extra project whose path contains spaces. It then exercises:

1. The intentionally broken Clear All behavior and real Provider screenshots.
2. Real `run_handoff.py`: output without confirmation remains **Pending**;
   simulated confirmation with a blocking review remains **Recirculate**.
3. Real `run_status.py`, its exact emitted Console launcher argv, and browser
   navigation. The Repair Packet keeps the blocker, owner, invalidated-evidence
   set, resume stage, and recapture requirement, and copies the exact Agent
   command through the real clipboard. Status reads and Console actions do not
   write project files.
4. A deterministic repair **outside** the Console, all three inbox user paths,
   fresh Provider captures, a replacement review fixture, and Console refresh.
5. Strict run validation, an explicit **Pass** handoff, unchanged point-back
   authority, byte-identical Fill in the deliverable and ZIP, five real viewport
   screenshots, and the same user paths against the delivered Fill.

The user paths cover completing by keyboard with focus transfer, cancelling or
confirming destructive clearing, empty-state recovery, and error/retry recovery.
Inspect `replay-result.json`, `console-complete.png`, and the run's `evidence/`
subtree inside the retained extra project. A failed assertion or subprocess
timeout must stay visible; never substitute fake captures to turn this gate green.

## Evidence boundaries

This is a deterministic integration regression, inspired by a prior local inbox
walkthrough. It does not execute model generation or collect real human approval.
Review, confirmation, and contract-binding inputs are test fixtures. Browser
assertions precede fixture verdict updates; they do not make those inputs an
independent design review. The test does not prove visual taste, real-device
behavior, provider/model quality, or an authorized external trial. Run Console
therefore remains **experimental, local, and trial-gated**.

The complementary continuation matrix covers completed/blocked runs, stale or
inconsistent bindings, capability mismatch, Pending, and missing/ambiguous Fill.
The Console security and browser suites remain required; this happy-path repair
journey does not replace them or introduce another status parser.

## Review and second-round verification

For an acceptance batch, retain commands, exit codes, counts, and raw logs in
local ignored storage; publish a self-contained delivery summary, not private
planning files. State the reviewed base and scope, including working-tree and
new files, and distinguish self-review from an independent review.
Resolve findings explicitly and rerun affected gates (and the full matrix when
scope changes). Record unrun checks and remaining gaps rather than promoting a
partially verified run to Pass. Contributors choose their own review workflow;
these requirements concern observable delivery evidence.
