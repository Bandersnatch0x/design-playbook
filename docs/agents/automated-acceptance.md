# Automated operator acceptance

The required test inventory is [CI](../../.github/workflows/ci.yml). Quick
validate/link/doctor checks are necessary but do not replace its Python and
Chromium matrix. Formal Standards and Spec review starts only after that matrix
is green. Missing Chromium is a failed gate, not an accepted skip.

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
   navigation. The Repair Packet keeps the blocker and owner, shows unproduced
   invalidation-detail/resume facts as unknown, and copies the exact Agent command
   through the real clipboard. Status reads and Console actions do not write
   project files.
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

For an acceptance batch, retain full-matrix commands, exit codes, counts, and logs
under `.scratch/`. Review Standards and Spec separately against a pinned base,
including working-tree and new files. If delegated, use the delegation channel
and reviewer authorized by the user. Resolve findings explicitly, rerun affected
gates (and the full matrix when the scope changes), then use a fresh reviewer for
second-round verification of fixes and evidence. Record remaining gaps rather
than promoting a partially verified run to Pass.
