# ADR-0045: External-evidence spend gate until the trial gate is satisfied

Accepted (roundtable verdict A with user preauthorization 「全部按推荐」,
2026-09-22). Implements the capability-freeze recommendation shared by all six
product audits (2026-09-21); tightens, not replaces,
[ADR-0043](0043-product-beachhead-and-operator-continuation.md).

## Context

Six independent audits converged on one structural deficit: external
validation is ≈ 0 (one participant miss, all dogfood runs maintainer-run,
catalog paused), while 27 days of post-baseline releases flowed into work the
roadmap lists as non-goals — adapter breadth, compatibility matrices, and
architecture deepening rounds. ADR-0043 already ruled that "adapter breadth
does not outrank the primary journey"; the audits show the rule was not
binding on effort. The failure mode is specific: coding agents push marginal
engineering cost to near zero, so output drifts toward whatever machines do
cheaply unless a spend gate makes the mainline the only open lane.

## Decision

1. **Until `G-RO-TRIAL-PASS` is satisfied by real external evidence** (per
   `docs/agents/run-console-read-only-trial.md`), no new capability work is
   started in the package: no new skills, commands, gates, rule-registry
   entries, collectors, Console capabilities, or adapter matrix rows.
2. **Agent-side effort is limited to three lanes:** (a) the diagnostic
   export instrument ([ADR-0044](0044-diagnostic-export-contract-v1.md)),
   which makes the trial measurable; (b) repairs that unblock the external
   trial or the trial's evidence path; (c) documentation, drift, and
   positioning normalization. Bug fixes, security-gate repairs, and release
   transactions of already-shipped capability remain in scope — this is a
   spend gate on new capability, not a freeze on correctness.
3. **The gate lifts automatically** when `G-RO-TRIAL-PASS` is satisfied with
   real evidence, and it ends no later than the Day-90 review (about
   2026-11-23), which rules pass / repair / stop against the roadmap
   acceptance floor. An empty exported-evidence set at Day-90 is a valid
   stop result.
4. **Early-stop clause:** if no new unrelated participant enters the
   comprehension check within 30 days of ADR-0044's acceptance, the stop
   review is triggered early rather than awaited.
5. **Adapter breadth is frozen at 30 rows** by the
   [ADR-0042 amendment](0042-multi-platform-adapter-generator.md) of the same
   date; this decision gives that freeze its policy basis.

## Consequences

- The roadmap governance section carries the same rule so the constraint is
  readable from the strategy document, not only from the ADR index.
- Internal roundtable rounds during the gate may only rank candidates drawn
  from these three lanes; a new benchmark scan that proposes capability work
  fails this decision and is recorded as such.
- If the trial resumes and passes, the next capability batch still goes
  through normal decision discipline; lifting the gate re-opens the lane, it
  does not pre-approve anything.
