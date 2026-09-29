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

## Amendment (2026-09-24): explicit self-use pause

The maintainer explicitly paused catalog submission and recruitment on
2026-09-24. This preserves the spend
gate and requires explicit resumption during the pause; neither the review
date nor internal dogfood automatically authorizes capability work. The
30-day checkpoint is approximately 2026-10-22, measured from ADR-0044's
2026-09-22 acceptance, not a condition already met on that acceptance date.

## Amendment (2026-09-25): bounded self-use exception

The maintainer explicitly authorized a read-only extension of the existing
run-status entry point: declared change scope to criterion mapping, evidence
gap summaries, and a re-verification proposal that retains every owner
requirement. This is a narrow exception, not satisfaction of the external
trial gate. Snapshot v1, persistent contracts, Console capabilities, and
execution/approval authority are unchanged; no collector or gate is added.
The existing G6 binding check rejects conflicting latest manifest entries
rather than choosing one arbitrarily.

Self-use paired measurement may be prepared, but insufficient real samples
must remain insufficient; deterministic tests cannot establish time savings.
Catalog submission, recruitment, and other new capability work remain paused.

## Amendment (2026-09-26): personal local asset-workbench implementation exception

The maintainer explicitly authorizes implementation and local validation of
one independently distributed, loopback-only asset workbench for a single
personal maintainer. This is an exception to the spend gate, not evidence that
G-RO-TRIAL-PASS has passed and not a reopening of the general capability
lane.

The authorized product boundary is:

- project-scoped local-folder registration with explicit path confirmation,
  plus the project-bound slash entry-point changes needed to select the same
  target when the plugin is installed at project or user scope;
- import, search, immutable asset revisions, explicit cross-project reuse,
  design-system and component maintenance, personal canvas composition,
  design orchestration, archive/delete lifecycle, and backup/restore;
- maintainer-approved repository change proposals with complete diffs,
  baseline hashes, recoverable application, and no automatic commit, push, or
  publication; and
- scoped Agent handoff and result intake, while the maintainer retains target,
  permission, publication, design-decision, and acceptance authority.

Authority remains partitioned. The workbench owns only its project registry,
asset metadata and revisions, canvases, orchestration records, tasks,
proposals, and lifecycle data. Existing baseline, distillation, preview,
evidence, evaluator, and run owners remain authoritative for their current
facts; the workbench may keep source locators and projections or call narrow
typed bridges, but may not create a second verdict, baseline, evidence, or
arbitrary-file authority. Read, write, execute, and model-send grants are
separate and are checked at the operation boundary.

The exception excludes member invitation, team roles, multi-user or real-time
collaboration, LAN or public hosting, cloud accounts or sync, new adapter rows,
general Console expansion, new collectors or gates, catalog submission, and
participant recruitment. It does not authorize a reading-demo site or a
replacement terminal CLI. The existing plugin CLI remains unchanged; the new
surface is a local service with Web UI and the bounded slash integration above.

Authorization to implement is not a completion claim. Delivery requires a
clean installation, all declared positive and negative acceptance paths,
real Windows and CI-platform evidence where platform semantics differ, real
Agent-host journeys rather than protocol mocks, full repository test gates,
and review that confirms the authority partition above. A missing, blocked, or
unrun required path leaves the capability undelivered. Commit, release,
catalog submission, recruitment, and publication still require their normal
separate decisions.
