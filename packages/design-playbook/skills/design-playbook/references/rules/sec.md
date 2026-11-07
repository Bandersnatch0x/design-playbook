<!-- Rule-registry part, located by ../rules.md -->

## SEC-01 — Sensitive-operation safety experience

```yaml
id: SEC-01
version: 2
title: Sensitive-operation safety experience
statement: Every dangerous operation offers at least one proportionate safety exit. Reversible operations prefer immediate undo over a confirmation step. Irreversible or unexpected losses require a confirmation that states the consequence. Undo names what it reverses, shows its result on screen, and supports more than one step. Sensitive values are masked by default (observable). Unguarded irreversible actions cause permanent loss, while confirmation on every routine delete trains users to click through warnings (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: hard-constraint
applicability-applicable: domain or spec declares sensitive data or dangerous operations
applicability-not-applicable: declared scope has no sensitive surface (observable reason required, e.g. no sensitive operation added)
applicability-blocked: sensitivity or reversibility cannot be determined from existing declarations (the declaration gap is itself a finding routed to D1)
check-type: protocol-check
check-inputs: interaction traces of dangerous operations. Source confirmation and undo bindings. Domain declarations of reversibility
signals-rendered: an irreversible operation with no confirmation. A reversible routine delete gated by a confirmation instead of undo. Undo that does not say what it reverses, or whose result lands off screen without being revealed. Single-step undo where a sequence was performed. Sensitive values in clear text
signals-source: destructive triggers with neither a confirmation nor an undo binding. No audit exit where the domain declares one
evidence-layers: interaction>=1, source>=1
evidence-method: runtime-observation
severity-default: S3 / fact
exceptions: declared controlled-environment rehearsal operations backed by a domain declaration. Assistive or simplified modes declared in the spec may require double confirmation
false-positives: a global undo history that covers the operation outside the visible surface. Verify the history before flagging
owner: domain -> R1; components -> R4
provenance: first-party
status: advisory
fix: classify each dangerous operation as reversible or irreversible in the domain declaration. Give reversible ones labeled multi-step undo that reveals its result. Give irreversible ones a consequence-stating confirmation. Mask sensitive values.
related: SEC-02@1
history: 1 | 2026-08-14 | docs | initial registry registration, placeholder entry with explicit applicability predicate (never silently skipped); 2 | 2026-10-10 | docs | resolve statement-versus-signal conflict (any proportionate exit), add undo quality, align with domain declaration of reversibility
```

## SEC-02 — Confirm and dismiss semantics

```yaml
id: SEC-02
version: 1
title: Confirm and dismiss semantics
statement: Temporary views (dialogs, sheets, popovers, confirmation prompts) can always be dismissed safely, the Escape key cancels them, the Return key triggers only a non-destructive default, and a destructive action is never the default or the sole visually primary control (observable). Wrong defaults turn a reflexive keypress into data loss (user impact).
capability-domain: D4
executes-in: D4:interaction
authority: hard-constraint
applicability-applicable: run has Fill output containing a dialog, sheet, popover, or confirmation prompt
applicability-not-applicable: planning-only run, or no temporary view in the audited scope (observable reason required)
applicability-blocked: keyboard walkthrough of temporary views unavailable
check-type: protocol-check
check-inputs: keyboard walkthrough (Escape, Return, Tab order) of every temporary view. Source button roles and default bindings
signals-rendered: Escape does nothing or commits. Return triggers a destructive control. A destructive confirmation with the destructive control focused by default. No visible cancel path. Confirm labels that do not name the consequence (generic yes, OK, or confirm wording). Closing a view with unsaved user content discards it without a choice. A second dialog stacked over a first
signals-source: destructive buttons bound to the default or primary variant. Missing Escape handler on dialog roots. Cancel styled as the primary variant while confirming a destructive action the user did not deliberately choose
evidence-layers: interaction>=1, source>=1
evidence-method: runtime-observation
severity-default: S3 / fact
exceptions: when the user deliberately chose a destructive command and the prompt only restates it, the confirm control may keep neutral styling and Return may confirm, provided the action is reversible or its consequence is stated. Purely informational notices may use a single acknowledgment control
false-positives: Escape intercepted by an inner editor that consumes it first. Verify the second Escape reaches the view
owner: components -> R4; domain -> R1
provenance: benchmark-input-only
status: advisory
fix: bind Escape to cancel on every temporary view. Give the default role only to a non-destructive control. Label confirm controls with the consequence verb. Offer save or discard when closing would lose user content. Never stack temporary views.
related: SEC-01@2, CRAFT-01@1, COPY-01@1
history: 1 | 2026-10-10 | docs | initial registration, benchmark-informed dialog semantics entry in first-party wording
```
