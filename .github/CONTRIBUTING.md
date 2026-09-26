# Contributing

[中文](CONTRIBUTING.zh-CN.md)

design-playbook is a plugin for evidence-backed UI delivery. This guide
covers repository contributions, not installation or product usage.

## Current scope

The project is in maintainer self-use and maintenance. Catalog submissions
and participant recruitment are paused by explicit maintainer decision.
Correctness, security, and documentation/drift work remain in scope. New
capability proposals need explicit, bounded implementation authorization
under [ADR-0045](../docs/adr/0045-external-evidence-spend-gate.md); a spec or open
ticket is not that authorization. Resumption requires an explicit decision.
Internal runs and automated fixtures do not satisfy external trial gates.

## Orientation

Start with [AGENTS.md](../AGENTS.md), [CONTEXT.md](../CONTEXT.md), and the
relevant [ADRs](../docs/adr).

Specs, plans, research, and independent work tickets are personal development
artifacts: keep all of them local, outside `docs/`, and out of Git. This maintainer
uses ignored `.agents/` directories; other contributors need not adopt that layout,
metadata format, or workflow. Public instructions and delivery summaries must be
readable in a fresh clone without local planning files.
Keep personal assets, root `.claude/` commands/settings, and `.scratch/` output
out of commits. Root and package `.claude-plugin/` directories are public plugin
metadata, not personal configuration. The existing tracked
`.agents/plugins/marketplace.json` is the sole exception within `.agents/`. A run's
`.scratch/<run>/plan.md` is a product artifact, not a repository work plan.

## Work routing

1. Route the work using the [issue policy](../docs/agents/issue-tracker.md).
   GitHub Issues are for user reports and feedback only, not internal work
   tickets. For defects, include expected and actual behavior, package/host
   versions, a minimal reproduction, and redacted evidence. Keep internal
   planning local. User feedback does not authorize new capability work.
2. For non-bug work, agree on scope before implementing. Record the intended user
   outcome, non-goals, authority boundaries, dependencies, and observable
   acceptance criteria. Resolve decisions in an ADR when they change a
   contract or cross-module authority. Proposed specs do not override ADRs.
3. Confirm implementation authorization and open blockers before editing.
   Choose your own working method; shared requirements concern documents
   and delivery evidence, not personal workflows or installed skills.
   Keep changes scoped and preserve unrelated work.
4. Implement a complete, narrow user path with regression tests at the
   existing public interfaces. Include validation and remaining limitations
   in the delivery summary; do not mark unrun checks passed.

## Documents and delivery

The [documentation index](../docs/README.md) routes readers by subject:
architecture explains composition and authority, subsystems explain current
behavior and contracts, development/testing explain contribution and validation,
and `docs/adr/` holds shared long-lived decisions. `docs/agents/` contains shared
maintenance conventions. Release/deprecation records retain historical facts.
Create a user guide or cookbook only when there is a real reader task; no empty
category scaffolding. Personal planning and this task's local governance records
are not published under another document type.

Each fact has one owner. Link to runtime schemas, generators, and CI instead of
copying their inventories. Update the owning explanation with behavior changes.
Generated sections must identify their generator and freshness check; do not label
hand-written interpretation as generated. English/Chinese pairs change together.
The link checker cannot verify semantic equivalence or decision authorization.

Delivery summaries include scope, observable acceptance results, actual checks,
unrun items, and remaining limitations. A private spec/ticket cannot be the only
way to understand the change. Before moving or removing shared documents, inspect
inbound links and unique information, preserve needed content, and obtain deletion
authorization. Do not rewrite release history as current state. The link gate
rejects public dependencies on private files and forced Git additions of personal
artifacts; `.gitignore` alone does not untrack existing files. The explicitly
authorized historical issue migration is local and untracked. It does not
authorize ongoing mirroring or deletion of future user reports; see the issue policy.

## Validation and release

Run the narrow affected tests first, then the quick gates:

```bash
python scripts/validate.py
python scripts/check_doc_links.py
python scripts/doctor.py --skip-self-check
```

README audit wording changes also require
`python -m pytest -q tests/test_audit_preferences_prose.py`.
The complete pytest and Chromium end-to-end matrix is owned by
[ci.yml](workflows/ci.yml), with execution guidance in
[automated acceptance](../docs/agents/automated-acceptance.md). Quick gates
alone are not complete acceptance. State what ran, its result, and what did
not run. Include relevant screenshots for user-facing UI changes.

`main` is the stable distribution channel. Release only through the
[release checklist](../docs/agents/release-checklist.md); this guide does
not authorize a release, catalog submission, or external trial.

## Boundaries

- The installable product is `packages/design-playbook/`; sibling packages
  are compatibility launchers or bridges. Declaration SSOT lives in the
  package's `skills/*/references/*`. Reuse the existing authority owner.
- Product prose and examples are first-party. Absorb external ideas in
  original wording; follow AGENTS.md's external-name and attribution rules.
- Generated `.codex-plugin/` and `codex/AGENTS.md` snapshots are not hand-edited.
  After a version change, run
  `python packages/design-playbook/scripts/generate_adapter.py codex` and
  verify drift gates. Do not churn generated files for unrelated prose edits.
- Keep English and Chinese README/contribution facts aligned. Local planning
  stays private; publish only the necessary durable explanation and decision,
  not the planning file. Link instead of maintaining duplicate normative copies.
- Keep secrets, credentials, raw private project data, and personal paths out
  of reports and commits. No hidden telemetry or automatic upload. Check the
  diff, including screenshots and logs, before sharing.
