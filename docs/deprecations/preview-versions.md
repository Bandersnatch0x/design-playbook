# Preview versions deprecation and removal checklist

## Status

Compatibility-only lifecycle, accepted via
[ADR-0027](../adr/0027-preview-versions-lifecycle.md) (architecture second
confirmation, 2026-08-11). Preview named versions, timeline replay,
historical state, and fork behavior shipped in v0.11.0 and are now frozen:
no new authoring command, in-repo caller, schema, or feature behavior is
added.

Physical removal of
`packages/design-playbook/mcp/preview/versions.py` is **out of scope** for
the current cycle and is targeted for v1.0.0.

## What is frozen

`versions.py` accepts no new:

- **authoring command** - the writable surface is `create_named_version` and
  `fork`; no new write/create entry points;
- **caller** - production code may not call `create_named_version` or `fork`;
  tests remain the only exerciser of authoring;
- **schema** - `VERSION_SCHEMA_VERSION` stays `1` and `VALID_KINDS` stays
  `{confirmed, revised, custom}`;
- **behavior** - the public function surface is locked.

A regression guard,
`packages/design-playbook/mcp/preview/test_versions_freeze.py`, locks the
frozen surface and fails if a new authoring caller, authoring function, or
schema constant appears.

## What is preserved (read behavior stays compatible)

The following read and projection behavior remains available and tested so
existing on-disk artifacts (`version-<seq>.json`, `decision-round-*.json`,
`confirm-round-*.json`, `round-*.html`, `fork.json`) stay readable:

- `state_at(preview_dir, round_n)` - replayable historical state;
- `timeline(preview_dir)` - unified decision + version event view;
- `list_versions(preview_dir)` - named versions, ascending seq;
- `render_versions_log(preview_dir)` - `log.md` projection incl. versions;
- `refresh_version_projection(preview_dir)` - repair/rebuild `log.md`;
- `fork(...)` - derive an independent linear chain (shipped write path,
  exercised only by tests).

`transaction.py` keeps rendering compatible logs both with and without
existing version artifacts: `render_versions_log` degrades to the plain
decision log when no `version-*.json` files exist.

## Production dependency that blocks removal

`packages/design-playbook/mcp/preview/transaction.py`, in
`_commit_projections_unlocked`, imports `render_versions_log` from
`versions.py` and calls it on every committed decision. This is the single
production dependency on the versions module. The versions module cannot be
deleted while this import stands.

## Long-lived owner for compatibility reading and log projection

The long-lived owner is the **Preview decision transaction module**,
`packages/design-playbook/mcp/preview/transaction.py`. It already owns the
durable decision authority (`decision-round-*.json`, confirm records, and
the `log.md` projection) and already imports the versions log projection.
Before removal, compatibility reading and log projection must migrate to
this owner (or a successor module it owns) so that old artifacts remain
readable without `versions.py`.

Specifically, the following must move into the long-lived owner:

- `render_versions_log` (log projection incl. the versions section) - already
  imported by `transaction.py`; absorb it locally instead of importing it.
- The read-side helpers `_load_version`, `_valid_versions`, `state_at`,
  `timeline`, and `list_versions`, so historical artifacts stay readable
  after `versions.py` is deleted.

## Removal checklist (target: v1.0.0)

v1.0.0 is an explicit **project migration policy** target, not a requirement
imposed by Semantic Versioning. SemVer permits breaking changes during
`0.y.z`; the project chooses to keep versions compatible through v1.0.0
regardless, because the published contract, the production dependency, and
the artifact migration obligation outlive SemVer permission.

1. **Migrate log projection.** Move `render_versions_log` (and its
   `render_log` + versions-section composition) into `transaction.py` or a
   successor module owned by it. Replace the
   `from ...versions import render_versions_log` import in
   `_commit_projections_unlocked` with the migrated local implementation.
2. **Migrate compatibility reading.** Move `_load_version`, `_valid_versions`,
   `state_at`, `timeline`, and `list_versions` into the long-lived owner so
   existing `version-<seq>.json` artifacts remain readable without
   `versions.py`.
3. **Prove old artifacts stay readable.** Keep tests that read v0.11.0-era
   `version-*.json` and `decision-round-*.json` fixtures through the migrated
   owner. The existing `test_versions.py` cases must pass against the
   migrated implementation before any deletion.
4. **Drop the production import.** Confirm no production code imports from
   `versions.py`. The freeze guard in `test_versions_freeze.py` is the
   evidence (the `test_no_new_production_caller_of_authoring_functions` and
   `test_transaction_still_imports_log_projection` cases).
5. **Delete `versions.py`.** Only after steps 1-4 land and the full package
   suite is green.
6. **Record removal.** Note the deletion in the v1.0.0 release notes and
   supersede ADR-0027's removal section.

## Out of scope this cycle

- Physical removal of `versions.py` (the checklist above).
- Any new versions authoring command, caller, schema, or feature behavior.
- Changing ADR-0024's transaction primitive ownership or single lock policy.

## References

- [ADR-0027](../adr/0027-preview-versions-lifecycle.md) - Preview versions
  enter a compatibility-only lifecycle
- [ADR-0024](../adr/0024-preview-versions-primitives.md) - Preview versions
  primitives (transaction/versions seam)
- `packages/design-playbook/mcp/preview/versions.py` - frozen module
- `packages/design-playbook/mcp/preview/transaction.py` - long-lived owner
- `packages/design-playbook/mcp/preview/test_versions_freeze.py` - freeze guard
- `docs/research/architecture-deepening-issues/05-versions.md` - US-5
