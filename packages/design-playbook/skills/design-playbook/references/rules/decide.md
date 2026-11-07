<!-- Rule-registry part, located by ../rules.md -->

## DECIDE-01 — Anti-default direction check

```yaml
id: DECIDE-01
version: 1
title: Anti-default direction check
statement: Every compare or explore tier direction selection answers the self-check "is this the direction I would produce for any similar brief?" with brief-specific evidence (observable); habit-default directions make unrelated products converge on one look and erase the identity the brief asked for (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: advisory-aesthetic
applicability-applicable: the run's decision report carries at least one compare or explore tier DD entry
applicability-not-applicable: point-fix or record-only run whose decision report carries no compare or explore tier DD entry (observable reason required)
applicability-blocked: decision report absent or unreadable, so the run's tier composition cannot be established
check-type: protocol-check
check-inputs: decision report DD entries at compare or explore tier; bound baseline identity declarations; the dated self-default direction observations recorded in this entry
signals-rendered: the selected direction matches a dated self-default profile — as of 2026-08 (dogfood evidence, refreshable observations): a light slate background with white cards and a teal or blue accent on admin surfaces, or a dark ops console with muted blue or cyan accents — while the DD entry records no brief fact that demands it
signals-source: selection rationale citing no spec item, baseline declaration, or brief fact — wording that would justify the same direction for any brief
evidence-layers: decision>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: the brief or bound baseline explicitly declares one of the observed default directions as the wanted identity (the declaration outranks the anti-default heuristic)
false-positives: a conventional direction that the comparison matrix justified against brief axes; the check targets unexamined defaults, not convention itself
owner: design -> R3
provenance: first-party
status: advisory
fix: answer the self-check inside the DD rationale with brief facts, add at least one candidate that breaks the default profile before selecting, and refresh the dated observations when dogfood evidence shows the defaults moved
related:
history: 1 | 2026-08-28 | docs | initial registry registration, first-party decision-hygiene entry; default-direction examples recorded as dated, refreshable observations (2026-08, dogfood evidence)
```
