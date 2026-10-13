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

## Amendment (2026-10-10): maintainer decisions recorded

The maintainer confirmed on 2026-10-10 that every recommended decision in the
remediation plan is adopted. The ones this record governs:

- Defect repairs to the run console and the workbench, made in place, are not
  new gates or registry entries, so they sit outside the ADR-0045 freeze.
  They change no stage boundary here.
- Stage S is the authority for the spec track (Decision 2). `SEC-01` is revised
  in place to v2, not forked, because a fork would take the registry past its
  30-entry split limit before the split exists. The registry's threshold field
  uses the structured syntax, and the numbers the spec track proposed are
  adopted as this registry's own rules.
- Build and runtime (Decision 5): option (a), no build step, for Stage P. The
  choice for the run console and the workbench is made by the amendment that
  opens each of them, if one ever does.
- Stages R and W stay unauthorized (Decision 4).
- Only the maintainer opens a stage, by a dated amendment committed on its own
  (Decision 1). The rollback switch follows Decision 6 as written.
- Operating-system names are platform identifiers, not external design
  authorities, and the runtime's package names may appear in this record as
  code identifiers only. Where ADR-0007 and the external-terms rule disagree,
  the external-terms rule governs.
- The plugin's own-UI self-audit becomes its own record (ADR-0049), because it
  is a standing product rule that must outlive this migration.

Stage P is not opened by this amendment. It still opens only by its own
amendment after Stage S lands and the in-place repair batch is green.

## Amendment (2026-10-13): build and runtime decision for Stage P

The maintainer records the Decision 5 choice, so the build question no longer
stands between Stage P and its opening amendment. The choice is option (a), no
build step. For the run console and the workbench it is the default their
opening amendments start from; either may still choose option (b) if it says
why. It authorizes no change to those two surfaces now.

- **Runtime, pinned by digest.** The `react` and `react-dom` 18.3.1 production
  builds stay vendored under `mcp/preview/vendor/` and pinned by sha256 in the
  preview vendor test. That directory is the only copy the plugin package
  edits. A surface opened later reads those same files from the package, or,
  for the separately distributed workbench, carries a copy gated against the
  same digests. No runtime, package manager or bundler is fetched at install,
  build or run time, and no npm dependency is added.
- **No build step.** Components are plain scripts with type comments. Shared
  code is written as immediately invoked functions that attach to one
  `window.DPBUI` namespace, so classic scripts, module scripts and the Preview
  shell's inline assembly can load the same bytes. No markup-in-script syntax,
  no type compiler and no transpiled artifact is committed. Type comments are
  hints, not a gate.
- **Content-security policy unchanged.** The console and workbench shell
  policies keep `script-src 'self'` exactly as they are. When a surface loads
  the runtime or a shared module, it serves it as a same-origin file added to
  that surface's exact route allow-list, under the same per-resource policy its
  own scripts already get. Inline script, `'unsafe-inline'`, `'unsafe-eval'`,
  and hash or nonce allowances are not used. Policy tests compare the whole
  policy string instead of checking that it contains `script-src 'self'`, and
  assert that no `unsafe-` source appears. Browser tests that load a shell
  record `securitypolicyviolation` events and expect none. The Preview shell
  keeps inlining the pinned runtime and keeps its current headers. The
  workbench's sandboxed preview origin is not a shell and is not touched.
- **Shared code and its drift gate.** Shared UI code has one canonical,
  editable copy in the plugin package's shared directory, `mcp/_shared/`, which
  already holds the shared tokens and glossary. One sync script is the only way
  to copy it; it writes a sha256 lock file next to the workbench copies, which
  sit flat in the workbench's `web/` directory because its package data does
  not recurse. A root test asserts that every copy matches its canonical file,
  that any workbench runtime copy matches the pinned digests, and that the lock
  file matches the files on disk. The workbench refuses to start when its
  copies disagree with the lock, and the packaging test asserts that the lock
  and every copy are in the built distribution. Front-end contract constants
  are generated from the server modules and follow the same rule: regenerated
  and compared byte for byte with the committed file.

This amendment chooses the build and runtime only. Stage P still opens by its
own dated amendment, committed on its own, that names its files, exclusions and
acceptance evidence (Decision 1), once Stage S has landed and the in-place
repair batch is green on the merged tree.
