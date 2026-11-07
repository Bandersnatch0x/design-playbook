<!-- Rule-registry part, located by ../rules.md -->

## RESP-01 — Declared-viewport coverage

```yaml
id: RESP-01
version: 1
title: Declared-viewport coverage
statement: The implemented UI remains usable at every viewport the contract declares (observable); a surface that only works at one viewport fails users on declared target viewports (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: project-declaration
applicability-applicable: contract or capture contract declares target viewports and the run has Fill output
applicability-not-applicable: planning-only run with no Fill output (observable reason required)
applicability-blocked: no declared target viewport (the gap itself is a finding routed to D1/D2), or viewport capture unavailable at a declared viewport
check-type: protocol-check
check-inputs: capture contract viewport group; rendered captures per declared viewport; source responsive behavior
signals-rendered: layout breakage or unreachable actions at a declared viewport
signals-source: single-viewport-only implementation, fixed widths beyond declared maxima
evidence-layers: rendered>=1, source>=1
evidence-method: runtime-observation
severity-default: S2 / fact
exceptions: viewports explicitly declared out of scope in the contract
false-positives: pixel-perfect equality across viewports; only usable reachability is required
owner: spec -> R2; template -> R4
provenance: first-party
status: advisory
fix: implement or fix layout at each declared viewport; declare target viewports in the contract when the declaration is missing
related:
history: 1 | 2026-08-14 | docs | initial registry registration, first-party cross-cutting entry (responsive)
```
