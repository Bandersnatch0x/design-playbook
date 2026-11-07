<!-- Rule-registry part, located by ../rules.md -->

## PERF-01 — Perceived-performance feedback

```yaml
id: PERF-01
version: 2
title: Perceived-performance feedback
statement: Declared async operations carry perceived feedback in the tier the threshold assigns to their duration, plus a timeout exit (observable). Unindicated waits invite repeated triggers and erode trust (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: measured-threshold
threshold: placeholder-from = 300ms; indicator-from = 2s; timeout-at = 10s
applicability-applicable: spec L4 declares async operations and the run measurement layer is capturable
applicability-not-applicable: no async operation declared (observable reason required)
applicability-blocked: async declaration exists but the measurement provider is absent (perceived performance needs runtime measurement)
check-type: protocol-check
check-inputs: measurement-derived timing. Interaction traces. Spec L4 declarations. Threshold reading: under 300 ms no indicator; 300 ms to 2 s layout-stable placeholder; over 2 s indicator plus what is happening; over 10 s timeout with retry or cancel
signals-rendered: feedback tier that does not match measured duration. No timeout exit beyond 10 s
signals-source: trigger controls without busy or disabled bindings for in-flight operations
evidence-layers: measurement>=1, interaction>=1
evidence-method: runtime-observation
severity-default: S2 / fact
exceptions: declared background tasks that report completion through notification instead of inline feedback
false-positives: an operation measured once above a tier boundary due to cold start. Use the declared typical duration
owner: spec -> R2|R5
provenance: first-party
status: advisory
fix: map each async path to the tier in the threshold. Timeouts get retry or cancel exits. In-flight triggers get busy state. Missing duration declarations are findings, never a silent clear.
related: CRAFT-08@2, STATE-01@2
history: 1 | 2026-08-14 | docs | initial registry registration, placeholder entry with explicit applicability predicate (never silently skipped); 2 | 2026-10-10 | docs | threshold moved into the registry as single source; absent duration declaration no longer clears
```
