<!-- Rule-registry part, located by ../rules.md -->

## STATE-01 — Pending feedback

```yaml
id: STATE-01
version: 2
title: Pending feedback
statement: Asynchronous triggers and data-loading regions present pending feedback that names the operation while it runs (observable); a silent trigger or a bare anonymous spinner leaves users guessing whether the action registered and whether waiting is safe (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: usability-heuristic
applicability-applicable: run has Fill output and the surface contains asynchronous triggers or data-loading regions (form submits, fetch-driven lists, uploads)
applicability-not-applicable: planning-only run, or every visible operation completes synchronously within the interaction (observable reason required)
applicability-blocked: pending states cannot be reached or captured with the available evidence surface
check-type: protocol-check
check-inputs: rendered pending states per asynchronous path; source request and state handling that gates the pending branch
signals-rendered: an asynchronous trigger with no visible pending feedback; a pending region that does not name what is loading or processing (a page-wide bare spinner covering one field's request)
signals-source: request handling with no pending branch bound to a rendered region; a pending flag consumed by nothing visible
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / fact
exceptions: operations that complete and surface their result within a single frame on the audited device (the pending state would only flash); background prefetch not tied to a visible user task
false-positives: progress already carried by a dedicated inline region that names the operation; a verified baseline prescribing silent local mutations
owner: craft -> R4
provenance: benchmark-input-only
status: advisory
fix: bind each asynchronous path to a pending region that names the operation, keep it scoped to the region it concerns, and resolve it deterministically into the result or failure state (PERF-01 covers the pacing of the feedback itself)
related: PERF-01@2
history: 1 | 2026-09-19 | docs | initial registry registration, benchmark-informed state-completeness entry in first-party wording; 2 | 2026-10-10 | docs | authority recalibrated to usability-heuristic: a usability convention, neither taste nor a measured threshold
```

## STATE-02 — Zero-data presentation

```yaml
id: STATE-02
version: 2
title: Zero-data presentation
statement: Data-fed collection surfaces declare what users see when the list is empty on first load and after filtering (observable); a blank region forces users to guess whether data is still loading, absent, or broken, and hides the next action (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: usability-heuristic
applicability-applicable: run has Fill output and the surface contains a collection or list display fed by data
applicability-not-applicable: planning-only run, or no data-fed collection display in the audited scope (observable reason required)
applicability-blocked: empty states cannot be reached or captured with the available evidence surface
check-type: protocol-check
check-inputs: rendered first-load-empty and filtered-empty presentations; source empty-branch handling for the collection's data source
signals-rendered: the collection region renders with no content and no hint while its data is empty; an empty presentation that offers no next action or explanation
signals-source: empty-result branches that render no region content; a data source with an empty path unhandled in the UI layer
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / fact
exceptions: create-first surfaces whose documented initial state is intentionally the empty canvas itself; the empty presentation is the specified product behavior (spec or verified baseline)
false-positives: a populated skeleton resolving within the declared loading flow (judged under STATE-01, not here)
owner: craft -> R4
provenance: benchmark-input-only
status: advisory
fix: give every data-fed collection an explicit empty presentation that says what the region is for and offers the next action, visually distinct from the pending presentation (STATE-01) and from failure feedback (STATE-03)
related: STATE-01@2, STATE-03@2
history: 1 | 2026-09-19 | docs | initial registry registration, benchmark-informed state-completeness entry in first-party wording; 2 | 2026-10-10 | docs | authority recalibrated to usability-heuristic: a usability convention, neither taste nor a measured threshold
```

## STATE-03 — Failure feedback

```yaml
id: STATE-03
version: 2
title: Failure feedback
statement: Failed asynchronous paths present recoverable feedback that names what failed and the next action — retry, undo, or exit — instead of failing silently to the console or surfacing a raw exception trace (observable); users stranded at a failure without a recovery path abandon the flow or retrigger the damage (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: usability-heuristic
applicability-applicable: run has Fill output and the audited scope declares or triggers failure paths for asynchronous operations
applicability-not-applicable: run has no asynchronous failure path in the audited scope (observable reason required)
applicability-blocked: failure states cannot be reached or captured with the available evidence surface
check-type: protocol-check
check-inputs: rendered failure states per asynchronous failure path; source error handling bound to request or mutation paths
signals-rendered: an asynchronous action fails with no rendered feedback beyond the previous state; a raw exception or stack trace rendered to the user; a failure banner offering no retry, undo, or exit action
signals-source: error branches that only log to the console; a catch path with no bound rendered region or recovery action
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / fact
exceptions: diagnostic or operator surfaces where raw detail is the declared point (spec L1 or verified baseline); security-sensitive withholdings — still state what the user can do next even when the cause is withheld
false-positives: failure feedback deferred by a declared retry policy that still lands in a rendered recovery state; terse diagnostics for a declared expert audience (spec L1)
owner: craft -> R4
provenance: benchmark-input-only
status: advisory
fix: bind each failure path to a rendered recovery region naming what failed where safe and what to do next, with retry or exit always present; keep the tone even (COPY-03 covers the message wording)
related: COPY-03@2, STATE-01@2
history: 1 | 2026-09-19 | docs | initial registry registration, benchmark-informed state-completeness entry in first-party wording; 2 | 2026-10-10 | docs | authority recalibrated to usability-heuristic: a usability convention, neither taste nor a measured threshold
```

## STATE-04 — Transient feedback

```yaml
id: STATE-04
version: 1
title: Transient feedback
statement: Transient notices never carry the only copy of a failure or a required action, stay readable long enough, pause while hovered or focused, are announced to assistive technology at a level matching their urgency, and routine successes stay quiet unless the action is significant (observable). Notices that vanish too fast, or that bury the one critical message among trivia, leave users unaware of what happened (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: usability-heuristic
threshold: notice-visible >= 5s; action-notice-visible >= 10s; concurrent-notices <= 1count
applicability-applicable: run has Fill output that renders transient notices (toasts, snackbars, inline flashes)
applicability-not-applicable: no transient notice in the audited scope (observable reason required)
applicability-blocked: notice timing or live-region semantics cannot be captured with the available evidence surface
check-type: protocol-check
check-inputs: interaction trace with notice appearance and disappearance timestamps. a11y tree live-region roles. Source notice configuration. Threshold reading: auto-dismissing notices stay visible >= 5 s and pause while hovered or focused; notices carrying an action (undo, retry) do not auto-dismiss before the action is taken or dismissed, or >= 10 s when they must expire
signals-rendered: a failure shown only in an auto-dismissing notice with no persistent state. Notices that disappear before the threshold or while focused. Every routine save confirmed with a notice. Several notices stacked at once
signals-source: notice duration below the threshold. Missing live-region role, or an assertive role on routine information
evidence-layers: interaction>=1, source>=1
evidence-method: runtime-observation
severity-default: S2 / judgment
exceptions: native desktop targets that route background events to the operating system notification area by native-craft declaration
false-positives: a notice that mirrors a persistent inline state already visible. The persistent state is the record
owner: craft -> R4; components -> R4
provenance: benchmark-input-only
status: advisory
fix: keep failures and required actions in a persistent region, and use the notice only as a pointer. Meet the timing threshold, pause on hover and focus, use a polite live region for information and an assertive one only for failures, and drop notices for routine success.
related: STATE-03@2, PERF-01@2
history: 1 | 2026-10-10 | docs | initial registration, benchmark-informed transient-feedback entry; timing numbers are this registry's own rule
```
