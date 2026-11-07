# First-party UX rule registry

Product-level declaration shared by the whole pipeline (read-only at run time; runs only produce audit rows and findings that reference it). Entry blocks below are structured field blocks validated by the product-level G8 self-check (`validate.py`, repo scripts).

- `schemaVersion: 1`
- Split rule: when the registry exceeds 30 entries, or its entries span more than 3 capability-domain groups, split by group into per-group files plus an index, and migrate the G8 cross-file checks at the same time. ID prefixes are naming families, not split groups.
- Layout (2026-11-07): entries are stored in per-family part files under `rules/` (for example `rules/craft.md`); this file is the index and carries the global entry order. ID prefixes name the physical parts only — they are not capability-domain groups, so the >30-entry / >3-domain split trigger above is unchanged.
- Machine-checkable face: `id / version / capability-domain / executes-in / authority / applicability-* / check-type / evidence-layers / severity-default / owner / provenance / status / related / overrides / supersedes / threshold`. Protocol face (wording read by reviewers): `title / statement / check-inputs / signals-* / evidence-method / exceptions / false-positives / fix / history`; `evidence-method` is one of `expert-review | runtime-observation | static-inspection | machine-measurement`, and `statement`, `evidence-method`, `exceptions`, `false-positives` and `fix` are required.
- Exemption discipline (two layers; distinct from an entry's `exceptions` field, which is a rule-internal legitimate exception grounded in a declaration): a **run-level exemption** of an `advisory` rule is agent-recordable in the audit row or finding (`ID@version` + observable reason + evidence ref; a blank reason is illegal) and expires with the run. A **persistent exemption** of a machine-enforced rule is a user-only governance event — `exemption_granted` in `<project>/rules-governance.jsonl` pinning `ID@version` with rationale + risk — and whoever grants it must, in the same act, append the paired entry to the project decision log (`decisions.jsonl`, `field` = the rule ID): a governance-log exemption without its decision-log twin is an unrecorded governance decision. No calendar expiry; the exemption is re-reviewed on structural events only (rule version bump, supersession, or change of the declaration it rests on).
- Rule text is first-party original. External product names and third-party rule text never enter this registry.
- Authority semantics: hard-constraint and measured-threshold entries carry fact-class severity; measured-threshold entries carry a threshold field that is the single source for every number the pipeline uses for that rule; advisory-aesthetic entries carry judgment-class severity no higher than S2; usability-heuristic entries cover usability conventions that are neither taste nor measured, with severity no higher than S2; platform-convention entries stay at S2 or below.
- Threshold syntax: `threshold: <term> <op> <number><unit>; ...` with op one of `>= <= =` and unit one of `:1 px ms s % count`. Each term appears once. Prose explaining a number stays in `statement` or `check-inputs`.
- Entry text is version-pinned. Changing an entry's text without incrementing its
  `version` makes every `ID@version` exemption ambiguous, because the pin still
  resolves to the same version number over different words. A prose edit to an
  entry is a version bump plus a matching `history` line.

```registry-index
schemaVersion: 1
part: rules/a11y.md
part: rules/copy.md
part: rules/craft.md
part: rules/decide.md
part: rules/i18n.md
part: rules/perf.md
part: rules/resp.md
part: rules/sec.md
part: rules/state.md
order: CRAFT-01 CRAFT-02 CRAFT-03 CRAFT-04 CRAFT-05 CRAFT-06 CRAFT-07 CRAFT-08 A11Y-01 RESP-01 I18N-01 PERF-01 SEC-01 COPY-01 COPY-02 COPY-03 A11Y-02 CRAFT-09 CRAFT-10 DECIDE-01 STATE-01 STATE-02 STATE-03 A11Y-03 A11Y-04 A11Y-05 A11Y-06 SEC-02 STATE-04 CRAFT-11
```
