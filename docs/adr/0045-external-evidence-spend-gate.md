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

## Amendment (2026-10-03): bounded self-use exception for host-fixture editing

The maintainer explicitly authorized this bounded exception on 2026-10-03.
Implementation and local validation are limited to
`packages/design-playbook/tests/fixtures/visual-edit-host/**` and the
corresponding `packages/design-playbook/tests/preview/**` fixture tests:

- multi-file apply with all-or-nothing semantics;
- multi-file rollback on a failed post-write observation; and
- concurrent-applier rejection where the later applier fails closed.

The exception excludes real host framework/HMR integration, arbitrary external
asset hashing, cross-process crash-recovery guarantees, any plugin-side source
writer, multiplayer/real-time collaboration (still Phase 2), catalog submission,
and recruitment. The plugin gains no source writer; its `writesSource` boundary
remains false.

Authorization to implement is not a completion claim. This fixture-only
exception does not satisfy the external trial gate or authorize release or
publication; the ADR-0045 spend gate otherwise remains in force.

## Amendment (2026-10-03): bounded self-use exception (round 2: declared multi-asset binding and in-fixture crash recovery)

The maintainer explicitly authorized this second bounded exception on 2026-10-03.
Implementation and local validation are limited to
`packages/design-playbook/tests/fixtures/visual-edit-host/**` and the
corresponding `packages/design-playbook/tests/preview/**` fixture tests:

- binding a HOST-DECLARED set of local assets: the host names its asset set,
  every declared local asset participates in review/confirmation binding, and
  a changed, removed, or newly undeclared declared asset makes the pending
  batch stale or refuses the apply; and
- crash recovery inside the fixture: a write interrupted at a defined point
  leaves no partial state, and a restart reclaims or refuses per the existing
  explicit lock rules with an honest diagnostic.

The exception excludes real host framework/HMR integration and any real
project's build pipeline, third-party or CDN asset fetching/crawling, arbitrary
asset discovery, cross-process or OS-level crash guarantees beyond the fixture,
any plugin-side source writer, multiplayer/real-time collaboration (still
Phase 2), catalog submission, and recruitment. The plugin gains no source
writer; its `writesSource` boundary remains false.

Authorization to implement is not a completion claim. This fixture-only
exception does not satisfy the external trial gate or authorize release or
publication; the ADR-0045 spend gate otherwise remains in force.

## Amendment (2026-10-03): bounded self-use exception (round 3: real local host integration, Vite/React dev server)

The maintainer explicitly authorized implementation and local validation against
one named real host, `D:\code_space\design-playbook-share\opsbench-demo-host`,
on 2026-10-03. The authorized boundary is limited to:

- the plugin's existing read-only live-route Preview against that host's real
  Vite/React dev server;
- a host-side adapter, a HOST-DECLARED asset map, and real evidence placed ONLY
  under that host's `.scratch/visual-edit-host-real/`; and
- host-side source writes strictly limited to files named in that host's
  declared asset map, only after the existing hash-bound confirmation, starting
  with `src/App.css`.

The exclusions are: installing the design-playbook plugin into the host,
fabricating `.scratch` evidence, any commit or publish in the host, writes to
files outside the declared asset map, git operations in the host, CI/macOS
claims, and multiplayer/real-time collaboration (still Phase 2).

The plugin gains no source writer; `writesSource` stays false and the G5 boundary
is unchanged. Authorization to implement is NOT a completion claim. This is
one real host on one machine, not proof of arbitrary frameworks, other bundlers,
or other platforms; the ADR-0045 spend gate otherwise remains in force.


## Amendment (2026-10-03): bounded self-use exception (F2: Next.js host bridge proof)

The maintainer explicitly authorized this bounded F2 exception on 2026-10-03.
Implementation and local validation are limited to the named real host
`D:\code_space\idea_project\moemail`, using its Next.js dev server rather than
the previously exercised Vite host. The authorized boundary is:

- the plugin's existing read-only live-route Preview against that host;
- a host-side adapter, a HOST-DECLARED asset map, and genuine local evidence
  under that host's `.scratch/visual-edit-host-next/` only; all new host files
  remain within that directory; and
- host-side source writes strictly limited to declared files after the existing
  hash-bound confirmation, with one minimal property edit and restoration of
  the original bytes; temporary bridge integration uses declared existing
  configuration or layout files and is also restored.

The exclusions are: plugin installation into the host, fabricated evidence,
any commit or publish in the host, git operations in the host, writes outside
the declared asset map, changes to the host's `package.json`, and CI/macOS
claims. This does not authorize any plugin version, release, or publication
change, new skills or commands, cloud or telemetry services, or a second
state machine.

The plugin gains no source writer; `writesSource` stays false and the G5
boundary is unchanged. Authorization is NOT a completion claim. This is a
bounded proof on one Next.js host on one machine, not a claim of support for
all frameworks, bundlers, or platforms, and it does not satisfy the external
trial gate. The ADR-0045 spend gate otherwise remains in force.

## Amendment (2026-10-06): bounded self-use exception for the preview control-shell rework

The maintainer explicitly authorized, on 2026-10-06, a bounded rework of the
Preview control shell's button and mode surface. This is a rework of an
already-shipped surface, not a new capability, and it is authorized as an
exception to the spend gate rather than as evidence that `G-RO-TRIAL-PASS` has
passed.

The authorized boundary is:

- the Preview control-shell surface only: `mcp/preview/control.html`,
  `control.css`, `control.js`, `control.review.js`, `control.react.js`,
  `i18n.py`, and the preview tests that pin that surface;
- a pipeline of: consolidate two independent reviews of the current button and
  mode surface; produce a complete page design (layout, interaction, and every
  state) with the Stitch design tool invoked by the designated agent; pull the
  design artifacts local; subject the design to two further independent
  reviews; and implement only after those reviews pass;
- no release, tag, publish, catalog submission, or recruitment.

The exclusions are: any new skill, command, gate, collector, or adapter row
(including new Stitch-related capability in the package); any second source of
preview or review authority; any change to the ADR-0008 feedback-floor
semantics; any new MCP server or runtime shipped in the package; any change to
the G5 boundary or to the read-only live-route contract; Console, workbench, and
evidence surfaces; and any work outside the files listed above.

The plugin gains no source writer; `writesSource` stays false and the G5
boundary is unchanged. Authorization to design and implement is NOT a completion
claim: delivery requires both design reviews to pass, the full repository gates
to be green, and the existing test assertions to remain unweakened. This bounded
exception does not satisfy the external trial gate, and the ADR-0045 spend gate
otherwise remains in force.

## Amendment (2026-10-07): scope extension for the sandbox shortcut allowlist

The maintainer authorized, on 2026-10-07, extending the file list of the
2026-10-06 amendment by exactly one file: `mcp/preview/pin_bridge.py`, and within
it only the frame-side key allowlist (`FRAME_PASS_KEYS`) that decides which of
the parent's shortcuts are forwarded across the sandbox boundary.

Rationale: the reviewed work remapped the Select tool to `A` in the parent. The
frame-side allowlist was never updated, so `A` works with focus in the parent and
not with focus inside the sandboxed prototype - the reviewers reproduced the
split both times. The split cannot be closed from the parent side, because the
child's filter drops the key before the parent ever sees it.

Everything else in the 2026-10-06 amendment is unchanged: the same exclusions,
the same invariants (`writesSource` false, G5 intact, the ADR-0008 floor exact,
a single readiness owner, no new skills, commands, gates, collectors, adapter
rows, MCP servers or runtimes), and no release, tag, publish, catalog submission
or recruitment. Authorization is not a completion claim.

### Additional accepted field (2026-10-07): `inlineStyle` in selection snapshots

A second pi session held this path concurrently and, before ownership was yielded
and the paths frozen, added an `inlineStyle` field to the selection snapshot the
bridge sends for each selected element in `pin_bridge.py`. That is a second field
in the same border file, beyond the key allowlist named above.

The maintainer accepted it on 2026-10-07 rather than reverting, because that
session's reconnect fix depends on it: the child applies a style before sending
its acknowledgment, and when the acknowledgment is lost the parent has no pending
edit record, so on reconnect the child reports `31px -> 31px` and the existing
no-op filter discards the edit. The snapshot must therefore carry the element's
inline style so the parent can recover the original value.

The boundary is unchanged in kind: still `mcp/preview/` only, still no new skill,
command, gate, collector, adapter row, MCP server or runtime, still `writesSource`
false and G5 intact, still no release or publication. The field was authored by a
concurrent session whose work is uncommitted and unverified at suite level; it
carries no acceptance claim of its own and must still pass independent review on
the merged tree.
