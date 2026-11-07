<!-- Rule-registry part, located by ../rules.md -->

## COPY-01 — Active-voice control labels

```yaml
id: COPY-01
version: 1
title: Active-voice control labels
statement: Control labels state the action in active voice with a verb that names the visible result ("Save changes", not a generic submit word), and one action keeps one name across the whole flow (observable); mechanism words and drifting action names force users to guess what a control will do before pressing it (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface contains labeled actions or controls
applicability-not-applicable: planning-only run, or a display surface with no labeled control (observable reason required)
applicability-blocked: rendered copy or source string evidence unavailable
check-type: protocol-check
check-inputs: rendered control labels across the flow; source string resources; script-aware casing check — sentence case is a Latin-script convention, while CJK labels carry no case and are judged on verb-led directness instead
signals-rendered: labels naming a mechanism instead of the result (generic submit-style wording); the same action appearing under different names in different steps
signals-source: string resources holding synonyms for one action; Latin-script label strings cased as headlines where sentence case is the convention
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: control names fixed by the host platform's own convention (the platform convention outranks label rewording)
false-positives: a verified baseline brand voice that deliberately bends verb phrasing; record the baseline reference as the exception
owner: craft -> R4
provenance: benchmark-input-only
status: advisory
fix: rename each control to an active verb phrase stating its result, keep one name per action across the flow, and apply sentence case to Latin-script labels only (CJK labels stay verb-led without filler particles)
related: COPY-02@1
history: 1 | 2026-08-28 | docs | initial registry registration, benchmark-informed copy entry in first-party wording
```

## COPY-02 — User-side naming

```yaml
id: COPY-02
version: 1
title: User-side naming
statement: Interface nouns name the objects users control and recognize, not the system's implementation of them (observable); implementation vocabulary makes users translate between their task and the interface on every read (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: advisory-aesthetic
applicability-applicable: run has Fill output and the surface names objects or operations users act on
applicability-not-applicable: planning-only run, or a surface with no user-facing object naming (observable reason required)
applicability-blocked: rendered copy or source string evidence unavailable
check-type: protocol-check
check-inputs: rendered nouns on controls, headings, empty states, and messages; source string resources; spec L1 terminology list when declared
signals-rendered: storage or process vocabulary standing in for the user's object — a record, entity, or job where the user thinks in orders, photos, or reports
signals-source: user-visible strings reusing internal model, table, or field names verbatim
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: expert tools whose declared user base demonstrably speaks the implementation vocabulary (spec L1 declaration required)
false-positives: trade terms that look technical but are the user's own working language; verify against the declared user base before flagging
owner: craft -> R4
provenance: benchmark-input-only
status: advisory
fix: rename user-visible nouns to the objects users control (spec L1 word list when present) and keep implementation names inside code and logs; the bar holds across scripts — CJK nouns name the user's recognized object in the user's own words rather than loan-translating system terms, and Latin-script casing conventions never transfer to CJK naming
related: COPY-01@1
history: 1 | 2026-08-28 | docs | initial registry registration, benchmark-informed copy entry in first-party wording
```

## COPY-03 — Error-message tone

```yaml
id: COPY-03
version: 2
title: Error-message tone
statement: Error messages state what happened and the concrete next action in an even, direct tone (observable); apologetic, blaming, or vague error copy strands users at exactly the moment they need a recovery path (user impact).
capability-domain: D4
executes-in: D4:cross-cutting
authority: usability-heuristic
applicability-applicable: run has Fill output and the audited scope declares or renders error states
applicability-not-applicable: run has no error state in the audited scope (observable reason required)
applicability-blocked: error states cannot be reached or captured with the available evidence surface
check-type: protocol-check
check-inputs: rendered error states per failure path; source error strings and their recovery bindings
signals-rendered: error copy naming neither cause nor next action; apology or blame padding in place of the recovery step; one identical vague message across unrelated failures
signals-source: a single generic error string bound to many distinct failure paths; error strings with no associated retry, undo, or exit action
evidence-layers: rendered>=1, source>=1
evidence-method: expert-review
severity-default: S2 / judgment
exceptions: security-sensitive failures where the cause is deliberately withheld — still state what the user can do next
false-positives: terse diagnostics for a declared expert audience (spec L1); brevity is not vagueness when cause and action are both present
owner: craft -> R4
provenance: benchmark-input-only
status: advisory
fix: rewrite each error message to name the cause where safe and the next action always, drop apology and blame padding, and keep the tone even in Latin-script and CJK copy alike
related: COPY-02@1
history: 1 | 2026-08-28 | docs | initial registry registration, benchmark-informed copy entry in first-party wording; 2 | 2026-10-10 | docs | authority recalibrated to usability-heuristic: a usability convention, neither taste nor a measured threshold
```
