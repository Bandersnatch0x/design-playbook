# Run Console read-only invited trial — readiness protocol

Operational protocol for the fixed human comprehension check on the
read-only Run Console. This document prepares a trial; it does **not**
run one.

> **Status: TRIAL_NOT_RUN.** No participant has been recruited,
> contacted, timed, or observed. Nothing in this document or in the
> rehearsal test below is participant evidence. The rehearsal asserts
> readiness only.

Companion deterministic rehearsal:
`packages/design-playbook/mcp/run_console/test_read_only_trial.py`.
Decisions that bound this protocol:
[ADR-0036](../adr/0036-invited-trial-data-and-role-boundary.md),
[ADR-0037](../adr/0037-local-single-run-console-lifecycle.md),
[ADR-0038](../adr/0038-run-snapshot-contract-and-loopback-security.md);
sequence authority: the [roadmap](../roadmap.md) delivery order
(phase 4, "Run the external read-only invited trial").

## Scope and authority

- This protocol fixes **what** the invited comprehension check asks, how
  the 60-second measure is defined, how maintainer intervention is
  disclosed, and what a participant must review before sharing anything.
- Actual trial **execution is separately authorized**. It is incapable
  of agent self-certification: an implementation agent, fixture,
  browser test, or maintainer rehearsal can never satisfy the
  `G-RO-TRIAL-PASS` gate. The gate is satisfied only by an authorized,
  real read-only invited trial in which unrelated participants complete
  the fixed comprehension check (roadmap phase 4 exit gate:
  "Unrelated external users can complete the fixed comprehension check
  without hidden telemetry or raw-file reconstruction; interventions
  are disclosed").
- Until that separately authorized real evidence exists, the correct
  state of this program is **TRIAL_NOT_RUN**, and typed actions
  (RCV1-009+) remain locked.

## The fixed four comprehension questions

The check always asks exactly these four questions, in Snapshot order.
Every answer is bound to **Snapshot authority**: it must be derivable
from the validated Snapshot v1 document rendered by the Console session,
never from raw run files, and never from maintainer narration.

1. **Intent** — What was this run trying to achieve?
   Answer source: `intent.summary` (rendered as fact 1).
2. **Source verdict** — What did the evaluation conclude?
   Answer source: `evaluation.verdict` (rendered as fact 2). When the
   verdict assertion is not current, the correct answer is its
   availability label and reason (`Stale` / `Unknown` / `Inconsistent`
   with the recorded reason code), never a guessed verdict.
3. **Blocker source** — What is blocking this run (or which limitation
   set applies), and where is that recorded?
   Answer source: `evaluation.findings` / `limitations.items` (rendered
   as fact 3 plus the Evaluation and Limitations sections).
4. **Next owner** — Who owns the next action and what kind of action is
   it?
   Answer source: `nextActions.primary` owner and kind (rendered as
   fact 4 plus the Next actions section).

A trial answer that a participant can only produce by opening run files
outside the Console is a failed answer, even if factually correct: the
measure exists to prove the projection is understandable on its own.

## The 60-second measure

- The measure starts when the Console page has opened into its ready
  view (the four fact cards rendered) and ends when the participant has
  produced all four source-bound answers.
- **Pass** = all four answers found and stated within 60 seconds of the
  ready view appearing, without raw-file navigation.
- Timing is **human-observed and human-recorded only**. The Console
  product collects nothing automatically: no timers, no telemetry, no
  event logs, no hidden storage, no upload. The product has no
  mechanism that records when a participant looked at what.
- A run that needs longer than 60 seconds is recorded as a real result
  (a miss), not retried away.

## Maintainer-intervention disclosure

- An **intervention** is any assistance beyond the public install/use
  documentation that changes a run or helps derive an answer
  (ADR-0036 §11). Examples: editing run files mid-trial, restarting the
  session with different data, pointing at the fact card that holds the
  answer, or rephrasing a question to reveal the answer.
- Neutral questions that neither alter the run nor reveal an answer are
  not interventions.
- **Any intervention during a trial run must be recorded and
  disclosed with the result.** A rehearsed, assisted, or coached pass is
  not evidence of unassisted comprehension and must not be reported as
  one.
- The deterministic rehearsal below includes no participant and
  therefore no interventions; it is preparation, not a trial run.

## Privacy checklist (what a future authorized participant reviews)

Nothing below happens today. When trial execution is separately
authorized, before any data is shared, the participant must be able to
review exactly:

- **What the Console collects: nothing.** Installation and
  participation are **not consent**. There is no telemetry, analytics,
  event log, automatic timing collection, or automatic answer
  collection. Timing and answers are human-observed and human-recorded
  by the facilitator's notes only, and only during an authorized trial.
- **What a participant is asked to share, and only if they choose to:**
  an explicitly initiated Diagnostic export (per ADR-0036), previewed by
  the participant before sharing — and only once a Diagnostic export
  contract is separately accepted and implemented. Today that control
  is disabled in the Console and no export exists.
- **Participant identity:** no name, account, machine fingerprint, or
  hidden identifier is collected. Any pseudonymous participant
  identifier is created by invitation, retained by the participant, and
  supplied by them explicitly (ADR-0036 §8) — the product never
  generates, stores, or transmits one on its own.
- **What is never shared:** secrets, credentials, source code,
  unselected artifacts, and raw model reasoning are excluded from any
  export (ADR-0036 §3).
- **Where trial data lives:** if a trial is later authorized, exports
  land under the selected run's `trial-export/` subtree as non-Evidence
  and non-acceptance input; they never enter `evidence/`, a Manifest,
  or an Evaluator decision.

## Reproducible local rehearsal (deterministic, no participant)

Run from the repository root:

```text
python -m pytest -q packages/design-playbook/mcp/run_console/test_read_only_trial.py
```

The rehearsal starts a real session and loopback HTTP server on an
ephemeral `127.0.0.1` port, opens the real UI in Chromium exactly the
way an operator does (`<origin>/#token=<token>`), and verifies — for
each of five constructed run roots — that the four source-bound answers
are discoverable on the rendered page, with values taken from the
served Snapshot itself:

| Scenario | Constructed by | What must be discoverable |
| --- | --- | --- |
| Current Pass | shared pass-closed point-back fixture | all four answers current, build state `current` |
| Recirculate | shared recirculate point-back fixture | Recirculate verdict, the blocking finding, `agent`/`continue` next owner |
| Stale | point-back replaced mid-build (RCV1-005 parity mechanism) | verdict and next action labeled **Stale** with reason `source-changed-during-build`; stale Pass must NOT present as current; changed source disclosed |
| Missing/unknown | `contract-bind.json` removed | contract assertion **Unknown** with `source-missing` reason and degraded build state; known answers still render |
| Inconsistent | contract bind record violating its invariant | contract assertion **Inconsistent** with `invariant-violation` reason and its conflict; never rendered as a known contract |

The rehearsal also asserts **zero side effects** per scenario: the run
tree digest is byte-for-byte identical before and after, no file is
created anywhere in the rehearsal's temporary roots, browser storage
remains empty, every network request stays on the authenticated
loopback origin, and no request is anything but a read (GET/HEAD).

**What "ready" means:** for every scenario above, the correct
source-bound answers are present on the rendered page without
raw-file navigation, stale values carry their stale labels, missing
values render their availability and reason, and the read leaves no
trace. Readiness is the only claim the rehearsal can make. The module
ends with the explicit marker `TRIAL_STATUS = "TRIAL_NOT_RUN"`, and its
final test asserts the rehearsal never flips it and never emits any
satisfied `G-RO-TRIAL-PASS` record.

## Explicit non-claims

- No trial was run; no participant was recruited, contacted, timed,
  observed, or identified.
- No timing or answer data exists. The rehearsal measures
  discoverability only and contains no participant-timing simulation.
- A green rehearsal is **not** trial evidence and does not satisfy
  `G-RO-TRIAL-PASS`.
- Nothing here authorizes RCV1-009 (typed actions) or any later
  ticket; the authorized frontier of the implementation chain ends at
  this readiness protocol.
