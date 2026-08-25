# design-playbook roadmap

Status: canonical strategy and rolling commitment, accepted 2026-08-25.

This roadmap separates facts from commitments and possibilities:

| Horizon | Meaning | Change control |
| --- | --- | --- |
| Delivered present | Capability available in the current formal release | Must be supported by released package inventory and checks |
| Rolling 90 days | The only delivery commitment | Re-baselined only through an explicit evidence review |
| Conditional 12-month north star | Falsifiable product branches, not promised dates or scope | Each branch stays in discovery until its entry conditions hold |

The current public promise is **evidence-backed UI delivery for coding agents**.
**Design I/O** names the mechanism. “Design OS”, “CI/CD for AI-generated UI”,
and “Workspace” are not current product claims.

## Strategy

The next user to win is a frontend or product engineer using Claude or Codex
to deliver UI in a real product repository. That person is the initial
**Run operator**, not a universal approver. Product, design, and engineering
Semantic approvers retain authority for the normative claims in their roles.

The near-term product result is deliberately narrow:

> A Run operator can understand the intent, source verdict, blocker source,
> and next owner within 60 seconds, complete a
> `Recirculate → repair → Pass` loop, and later choose to use the workflow for
> another real UI work item.

The visible surface for this result will be a source-linked projection over
existing authorities. It will not introduce a writable `DesignRun` aggregate
or copy decisions, Evidence, Findings, confirmations, or verdicts into a new
source of truth. See [ADR-0035](adr/0035-run-view-projection-authority.md).

## Delivered present

As of 2026-08-25, the formal public release is `v0.20.2`. The shipped product
is an installable Claude Code / Codex plugin, not a standalone application or
hosted service. Its released surface includes:

- the Design I/O pipeline of declarations, contracts, implementation review,
  criterion-bound Evidence, point-back, and bounded recirculation;
- run-scoped artifacts under `.scratch/<run>/`, with run status derived from
  durable artifacts rather than an independent run-state store;
- bundled optional Preview and Evidence MCP runtimes;
- `execute_capture_plan` as the single runtime Provider seam: the Provider
  produces Artifacts, the Manifest binds them to Criteria, and the Evaluator
  owns Findings and the source verdict;
- namespaced skills and commands for shaping, implementation, review, status,
  and installation diagnosis.

The exact installed surface and current operating model remain documented in
the [README](../README.md), [product definition](../PRODUCT.md), and
[domain context](../CONTEXT.md). Unreleased branches and active workstreams do
not count as delivered merely because they exist in this repository.

> **Not delivered:** the Closed-loop Run Console, Run snapshot v1, typed
> Console actions, Diagnostic export, and invited-trial program described below
> are planned work. They are not present-tense product capability.

## Rolling 90-day commitment

This horizon begins from the 2026-08-25 decision baseline. Day 90 triggers a
review; it does not automatically publish a beta, unlock the north star, or
convert unfinished work into delivered capability.

### Outcome and trial boundary

The commitment is to validate the near-term result on P2/P3 changes in
**existing Web products**, with the Evaluator enabled and at least one rendered
or interaction Criterion backed by a Manifest-bound Artifact. Greenfield work,
marketing-site generation, native mobile, desktop, multi-platform automation,
and Canvas workflows are outside this trial.

Only these definitions count toward the result:

- A **Qualified audited run** has the scope above, a final point-back record,
  and every Maintainer intervention disclosed.
- A **Voluntary repeat** occurs only when a participant independently starts a
  new Qualified audited run for a different real UI work item after the first
  run ends. Same-run repair, reopening the Console, repeated export, or a
  maintainer-scheduled demo does not count.

### Resource assumption

The horizon assumes **one primary maintainer plus coding agents**. Suggested
capacity allocation is:

- 50%: closed-loop reliability, Criterion/Evidence binding, and actionable
  Findings;
- 30%: Run snapshot, parity verification, and the Closed-loop Run Console;
- 20%: distribution, positioning, first-run quality, and invited trials.

Later platform branches do not become commitments without a stable,
explicitly committed 2–4 person team covering at least two quarters.

### Authority and evidence invariants

All work in this horizon must preserve the current ownership model:

| Actor | Owns | Must not claim |
| --- | --- | --- |
| Human Semantic approver | Intent, durable decisions, preference/rule promotion, exceptions, and role-scoped semantic acceptance | Reproducible machine facts outside human judgment |
| Deterministic validator | Hashes, bindings, structural gates, and reproducible metrics | What counts as good product or design intent |
| Agent | Proposals, implementation, repair suggestions, and learning candidates | Self-promotion or final confirmation |
| Runtime Provider | Captured Artifacts | Evidence binding, Findings, or verdicts |

A normative claim names a required product, design, or engineering approver
only when downstream acceptance depends on that judgment. A missing Role
attestation blocks only dependent results; there is no global three-role gate.
Attestation scopes a confirmation but does not prove identity, employment,
organization membership, or legal consent. Continuing a run never implies
approval in another role.

The horizon retains `execute_capture_plan` as the single Provider collector
seam. It improves Manifest binding, Evaluator reasoning, and visibility rather
than splitting capture and judgment across criterion-aware MCP tools.

### Delivery sequence and phase gates

Work proceeds strictly in this order. A phase cannot begin until the preceding
exit gate passes. Implementation tickets remain subject to the contract,
parity, and security gates; a UI is not evidence that those gates passed.

The committed order is: contract freeze → read parity → secured single-run
Console → external read-only trial → typed actions → expanded trial.

| Order | Deliverable | Entry condition | Exit gate |
| --- | --- | --- | --- |
| 1 | Freeze the Run snapshot and Diagnostic export contracts | ADR-0035 through ADR-0038 remain accepted and existing authority owners are mapped | A versioned domain contract defines values, availability, sources, freshness, errors, compatibility, and export boundaries without mirroring UI components or filenames |
| 2 | Establish deterministic read parity | Contract v1 is frozen | Fixtures map every projected assertion to an existing authority; missing, stale, partial, inconsistent, and source-change cases fail visibly; repeated rebuilds do not invent or strengthen semantics |
| 3 | Build the secured single-run Console | Read parity is proven | An on-demand, loopback-only session opens one explicit run, passes containment and request-security checks, and remains read-only |
| 4 | Run the external read-only invited trial | Console parity and security gates pass | Unrelated external users can complete the fixed comprehension check without hidden telemetry or raw-file reconstruction; interventions are disclosed |
| 5 | Add the typed-action allowlist | Read-only trial demonstrates that the projection is understood and each action has an existing authority owner | Only the approved typed actions are reachable; every write is routed to its owner and followed by a full snapshot rebuild |
| 6 | Expand the invited trial and evaluate graduation | Typed-action tests, privacy boundaries, and rebuild parity remain green | The acceptance floor and public-beta gate below both pass; otherwise the horizon ends in review, repair, or stop |

### Planned Console boundary

The planned **Closed-loop Run Console** is an on-demand local Web application
bound only to loopback. One session opens one explicitly selected run and ends
when its server session closes. A recent-run locator may help select a run, but
the Console is not a daemon, project dashboard, cross-run report, cloud
service, Canvas, or organization Workspace.

Each refresh builds one disposable, source-hash-bound Run snapshot. The
snapshot exposes domain assertions rather than raw artifact topology and
separates each assertion's domain result from its availability:
`known`, `unknown`, `stale`, or `inconsistent`. Partial writes, changing hashes,
missing authorities, and unknown values remain visible; the Console never
silently displays an older successful value as current.

Read parity precedes actions. The initial typed-action allowlist is limited to:

- refresh the snapshot;
- resolve and view a server-rendered, read-only authority excerpt;
- copy the next Agent command;
- request a claim- and role-scoped attestation through the existing authority
  owner;
- generate a participant-reviewed Diagnostic export.

The Console will not execute repairs, automatically rerun an Agent, edit
arbitrary artifacts, provide a generic run mutation endpoint, or write
acceptance. Role-attestation requests bind the claim identity and hash,
requested role, and current authoritative source hash; source changes
invalidate the request or prior attestation.

Loopback is an exposure boundary, not trust. The implementation must use an
unguessable session token, validate Origin, keep GET and HEAD side-effect-free,
protect fixed-schema action requests, constrain opaque Source locators to the
selected run, and fail closed on invalid tokens, versions, hashes, locators, or
payloads. See [ADR-0037](adr/0037-local-single-run-console-lifecycle.md) and
[ADR-0038](adr/0038-run-snapshot-contract-and-loopback-security.md).

### Invited-trial data boundary

The trial is local-first and has no hidden telemetry, account requirement,
machine fingerprint, or upload endpoint. Each participant explicitly initiates
and reviews a Diagnostic export, then shares it manually. An export is a
versioned JSON contract plus a Markdown view, stored under that run's
`trial-export/` subtree and marked as non-Evidence and non-acceptance input.

The export contains only the minimum facts needed to evaluate first-run
completion, closed-loop integrity, comprehension, elapsed time, disclosed
human intervention, and repeat use. Secrets, credentials, source code,
unselected artifacts, and raw model reasoning are excluded. See
[ADR-0036](adr/0036-invited-trial-data-and-role-boundary.md).

The comprehension check times four fixed answers against the Run snapshot:
intent, source verdict, blocker source, and next owner. Satisfaction and
interview notes may supplement this evidence but cannot replace it.

### Acceptance floor

The direction is evaluated only after all of these minimum quantities exist:

- at least 5 unrelated external participants;
- at least 3 real repositories;
- at least 10 Qualified audited runs;
- at least 5 completed `Recirculate → repair → Pass` loops;
- at least 3 of the 5 participants completing a Voluntary repeat within 30
  days;
- at least 80% of runs forming a complete Evidence loop without a maintainer
  manually editing run artifacts;
- at least 4 of 5 participants correctly identifying the fixed comprehension
  answers without opening raw run files, with median location time below 60
  seconds;
- fewer than 20% of real blocking Findings judged unactionable, false, or
  unable to point back to an owning declaration.

### Public-beta exit gate

Meeting the quantity floor is necessary but not sufficient. Public beta also
requires:

- zero competing writes introduced by the projection or typed facade;
- zero unexplained sensitive-data disclosures;
- 50 consecutive Run snapshot rebuilds with zero semantic drift;
- every parity, containment, action-owner, and fail-closed security gate still
  passing.

Elapsed time never substitutes for this gate.

### Stop and redirect conditions

- If fewer than 3 invited users achieve first-run success by day 45 after a
  qualified invitation, pause Console expansion and repair positioning,
  installation, or closed-loop quality first.
- If Voluntary repeat is below 40%, do not start general Design Memory.
- If the Run View does not materially improve comprehension or location time,
  stop the Design OS / Workspace direction and retain a CLI status summary.
- If more than 20% of real blocking Findings are unactionable, false, or cannot
  point back, pause Memory and Multi-Agent work and repair Criterion/Evidence
  semantics first.
- If any phase violates a current authority boundary, introduces competing
  writes, or cannot pass its security gate, stop progression and revise the
  contract or implementation before continuing.

### Explicit non-goals

The rolling horizon does not include:

- a writable `DesignRun` authority, permanent snapshot history, or generic
  run mutation API;
- general Design Memory or automatic promotion of learned preferences;
- a Multi-Agent runtime or speculative coordination layer;
- Canvas, persistent dashboard, cloud or organization Workspace;
- enterprise governance, accounts, authenticated organization identity, or
  hidden/public telemetry;
- public adapter ecosystem expansion or five specialized Evidence collectors;
- direct repair execution, automatic reruns, or automatic acceptance from the
  Console;
- greenfield, native mobile, desktop, or multi-platform trial coverage;
- a public claim that Design OS or CI/CD for AI-generated UI is delivered.

## Conditional 12-month north star

The north star is a possible evolution from a proven closed loop toward an
AI-native design operating layer: human intent remains authoritative, agents
execute through explicit contracts, runtime artifacts become criterion-bound
Evidence, failures point back, and confirmed learning can improve later work.

This is a **sequencing hypothesis, not a dated plan**. The candidate Phase 3–6
month labels are retired. Each branch requires a new review and, where it
changes authority, a superseding ADR.

| Conditional branch | Evidence required before commitment | Boundary that remains true |
| --- | --- | --- |
| Confirmed cross-run learning / Design Memory | The repeat-use gate passes and repeated decisions show a real cross-run need | Learning candidates remain derived; only explicit humans promote durable rules or preferences |
| Minimal run coordination for multiple Agents | At least two approved independent command writers need atomic coordination, or reproducible lost updates, duplicate effects, or recovery failures exist; replay parity and cutover/rollback are proven | A coordinator may own command identity, expected version, lease, cancellation, or ordering only; Contract, Preview, Manifest, Finding, and Verdict stay with existing owners |
| Multi-Agent design runtime | Closed-loop repeat use is proven, coordination need is real, and the 2–4 person staffing gate is met | Agent roles do not create semantic approval or self-promotion authority |
| Remote review or Design Workspace | Local Console value is proven and a separate decision defines identity, access control, consent, retention, deletion, and remote lifecycle | Workspace views do not become acceptance or run-state authority |
| Adapter ecosystem | Repeated user demand identifies a supported boundary and maintainers can test it | Adapters produce or translate typed inputs/Artifacts; they do not become rule or verdict authorities |
| Enterprise governance and audit | Organizations demonstrate demand after the local closed loop and identity model are proven | Governance makes authority explicit; it does not infer approval from activity or Agent output |

Failure of a branch condition is a valid roadmap result. It keeps that branch in
discovery rather than silently moving it into the next 90-day commitment.

## Relationship to doop, Figma, and React

design-playbook does not aim to clone Figma or compete with a human/AI Canvas
such as doop. It owns the tool-neutral delivery contracts, Evidence semantics,
Evaluator boundary, and point-back loop used by coding agents.

| Surface | Relationship |
| --- | --- |
| doop | Optional external design/review surface. It may exchange typed artifacts in a future conditional integration, but it is not a dependency, authority, or current delivery target. |
| Figma | Optional source or destination for explicit references and artifacts. Figma is not required for installation, intent, Evidence, or acceptance, and a future importer remains conditional ecosystem work. |
| React | A common implementation output for the first Web validation surface, not the product's domain model. A React adapter may be useful later, but core contracts remain stack-neutral. |

External references can reveal missing capabilities or conflicts. They do not
become first-party rules, product dependencies, or sources of truth.

## Roadmap governance

- Delivered claims advance only with a formal release and verified installable
  inventory.
- The 90-day layer is reviewed against exported evidence, not feature count or
  elapsed time.
- A new writer, remote surface, identity claim, or authority migration requires
  an explicit decision before implementation.
- The most specific accepted ADR wins over roadmap shorthand. The domain terms
  in [CONTEXT.md](../CONTEXT.md) remain canonical.

## Accepted-decision coverage

| Decisions | Roadmap location |
| --- | --- |
| Q1, Q12, Q27 | Three horizons; current public promise; delivered-present boundary |
| Q2, Q6, Q7 | Strategy; outcome and trial boundary |
| Q3, Q4, Q11, Q16 | Authority and evidence invariants; planned Console boundary |
| Q5 | Resource assumption |
| Q8, Q13, Q14, Q15 | Delivery sequence; planned Console boundary |
| Q9 | Authority and evidence invariants |
| Q10, Q17 | Invited-trial data boundary |
| Q18 | Acceptance floor |
| Q37 | Delivery sequence and phase gates |
| Q38 | Public-beta exit gate; stop and redirect conditions |
