# ADR-0048: Staged UI-runtime migration of the plugin's own surfaces

Accepted (maintainer-authorized 2026-10-10, when the maintainer approved the
UI remediation plan and its recommended decisions) as a bounded exception to
[ADR-0045](0045-external-evidence-spend-gate.md), not as evidence that
`G-RO-TRIAL-PASS` has passed. Acceptance opens Stage S only. Extends, and does not widen,
[ADR-0047](0047-preview-visual-editing-capability.md).

## Context

The plugin ships three operator surfaces: the Preview control shell, the run
console, and the separately distributed local workbench. Only the Preview shell
uses the vendored component runtime (`mcp/preview/vendor/`, digest-pinned by
the preview vendor test), written without a build step. The run console and the
workbench are plain scripts under a `script-src 'self'` policy.

A migration plan proposes moving all three onto one shared component layer.
Three records stand in its way. ADR-0045 freezes new gates and rule-registry
entries. ADR-0047 §4 keeps the console, workbench and evidence surfaces, and any
new runtime shipped in the package, out of scope. The workbench exception keeps
new gates out of scope. The plan also depends on thresholds (contrast, text
size, target size, notice timing) that the rule registry does not yet hold, so
a gate written against them would be a rule with no registry entry.

Earlier work on this branch wrote its authorization in the same commits as the
code. This record exists so that each stage is authorized before it is built.

## Decision

1. **Single decision authority.** Only the maintainer opens a stage, by a dated
   amendment to this record, committed on its own before any code for that
   stage. Agents, reviewers, a green CI run, or a passing previous stage never
   open a stage. Each amendment names its files, exclusions and acceptance
   evidence. A stage with no amendment is not authorized, whatever this record
   says about it.

2. **Stage S: specification prerequisites (opened by this record on acceptance).**
   Authorized: the registry additions and revisions listed in the spec track
   (new entries A11Y-03, A11Y-04, A11Y-05, A11Y-06, SEC-02, STATE-04, CRAFT-11;
   new versions of SEC-01, CRAFT-08, PERF-01, A11Y-02), a machine-readable
   `threshold` field, and the registry-level checks V-1 to V-6 in
   `scripts/validate.py`, each with a failing counter-example test. V-6 may read
   the workbench's shipped style sheets; this is the only gate this record adds
   to the workbench, and it is read-only. Promotion of any entry to
   `machine-enforced` stays a user-only governance event.

3. **Stage P: Preview control shell (opens by amendment after Stage S lands and
   the in-place repair batch is green).** Scope is the files ADR-0047 §1
   already names, plus their tests. The migration is an equivalence
   replacement: the behavior tests written by the repair batch are the
   acceptance floor and may not be weakened. The form/POST transaction, the
   one-time decision token, source-hash and route checks, and `writesSource:
   false` are unchanged.

4. **Stage R: run console, and Stage W: workbench (each opens by its own
   amendment, only after Stage P is delivered).** Neither is authorized by this
   record. The amendment that opens one must state why the in-place repair is
   insufficient for that surface, the build and runtime option it uses, the
   content-security-policy change, and how the runtime enters that surface's
   distribution with a pinned digest.

5. **Build and runtime: decision placeholder.** Before Stage P opens, the
   maintainer records one of:
   - (a) No build step. Components stay plain modules calling the runtime
     directly, with type comments; each surface loads them from its own origin.
   - (b) A pinned build step. Built artifacts are committed, and a gate rebuilds
     from source and asserts byte equality; any copy into the workbench
     distribution carries its own hash gate.
   Either way the runtime bytes stay digest-pinned, and no runtime is fetched at
   install or run time.

6. **One UI per session; a rollback switch.** Each migrated surface selects its
   UI once, at session start, through a server-side setting that defaults to the
   new UI after cutover and accepts `legacy`. The choice is recorded in the
   session metadata and cannot change mid-session. While both UIs exist, only
   the selected one can hold the decision token or submit; a shadow UI is
   read-only. A gate asserts that one session never exposes two submitters. The
   legacy path and the switch are removed in a separate commit one minor
   release after cutover.

7. **Excluded throughout:** evidence surfaces; any second source of preview,
   review, verdict or floor authority; any plugin-side source writer;
   multi-user or real-time collaboration; any new MCP server; any new skill,
   command, collector or adapter row; a hand-written front-end schema that
   duplicates the server contracts (front-end types are generated from them);
   release, tag, publish, catalog submission and recruitment; and any change to
   the ADR-0008 floor semantics.

## Consequences

- Stage S can land and close its own findings even if no runtime migration
  ever follows; the repair batch does not wait on this record.
- Thresholds live in one place. A gate that hard-codes a number the registry
  owns fails validation.
- The console and the workbench stay on their current code until a separate,
  dated decision says otherwise; declining Stages R and W is a valid outcome.
- Authorization to implement is not a completion claim. Each stage still needs
  the full repository gates, the browser matrix, a Windows run where platform
  semantics differ, and independent review of the merged tree. Host checks that
  were not run are reported as not run.
- This bounded exception does not satisfy the external trial gate. The ADR-0045
  spend gate otherwise remains in force, and its Day-90 review is not moved.
