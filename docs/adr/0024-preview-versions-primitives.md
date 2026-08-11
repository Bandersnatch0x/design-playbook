# ADR-0024: Preview versions primitives

## Status

Accepted (C6, 2026-08-09). Preview versions lifecycle and removal policy is
superseded by ADR-0027; transaction primitive ownership and lock policy remain
in force.

## Context

`mcp/preview/versions.py` (local version control over Preview decision
entries) reaches into `transaction.py` through its private seam: it imports
seven underscore-prefixed primitives (`_atomic_write`, `_directory_lock`,
`_json_text`, `_load_confirm_for_entry`, `_load_entry`, `_render_log`,
`_valid_entries`) next to the public `ConfirmRecordError`,
`DirectoryLockError`, and `PROJECTION_LOCK_NAME`. `transaction.py` owns the
durable-preview authority (ADR-0013): locks (`_directory_lock`,
`PROJECTION_LOCK_NAME`), atomic write, JSON projections, confirm/entry
loading, and log rendering. versions.py is its only cross-module consumer of
the private surface.

versions.py also re-declares its own lock-policy constant set —
`VERSION_LOCK_TIMEOUT_SECONDS` / `STALE` / `HEARTBEAT` / `POLL` — with values
identical to `transaction`'s `DIRECTORY_LOCK_*` defaults, then passes them
back into `transaction._directory_lock` through `_version_lock()`. Two
parallel constant sets that must agree are a desync surface: a future policy
change on one side silently leaves the other side on the old lease rules.
The lock *filename* (`.versions.lock`) is a legitimate second namespace;
the duplicated *policy* is not.

The reverse direction has the same shape: `transaction.py` lazily imports
`versions._render_versions_log` to build `log.md`, another private
cross-module reach.

## Decision

Take the conservative path: promote the shared primitives to each owning
module's public API, delete the duplicated lock-policy namespace, and keep
every other behavior byte-identical. A full rewrite (shared preview-store
module, both modules importing a third home) was considered and rejected:
it would still have to promote the same primitives to be useful, and it
spreads one authority across more files for no behavioral gain.

- `transaction.py` public API (leading underscore dropped, no aliases):
  `atomic_write`, `directory_lock`, `json_text`, `load_entry`,
  `load_confirm_for_entry`, `render_log`, `valid_entries`. The old private
  names are deleted, not aliased — every in-repo caller is updated, and
  there are no out-of-repo consumers of these underscore names (the
  compatible launchers only exec the bundled server).
- `versions.py` public API: `_render_versions_log` becomes
  `render_versions_log`, which `transaction.py` imports (public reverse
  seam). versions.py imports the promoted transaction primitives by their
  public names.
- One lock policy source: `_version_lock()` calls
  `directory_lock(preview_dir, VERSION_LOCK_NAME)` with `transaction`'s
  defaults — no parameter overrides, no second constant set. The
  `VERSION_LOCK_TIMEOUT_SECONDS` / `STALE` / `HEARTBEAT` / `POLL` constants
  are deleted; the values they carried are exactly `transaction`'s
  `DIRECTORY_LOCK_*` defaults. `VERSION_LOCK_NAME = ".versions.lock"` stays
  in versions.py: distinct lock files for distinct critical sections remain
  correct, the removed duplication was policy-only. If versions ever needs
  different lease timing, it passes explicit parameters to
  `directory_lock(...)` at the one call site — never a second constant set.

## Compatibility

Zero artifact, wire, or JSON-format change. Renames are internal to the
Python surface; entry schema stays v1, lock filenames and semantics are
unchanged, `log.md` projection text is unchanged. Preview contract suites
(`test_transaction.py`, `test_versions.py`, `test_integrity.py`,
`test_server_stdio.py`, browser/control tests) stay green.

## Consequences

- versions.py's reach through `transaction`'s private seam is gone; the
  durable-preview authority exposes its primitives deliberately.
- One lock-policy source: future lease-rule changes in `transaction` apply
  to the version writer automatically.
- The remaining underscore-prefixed symbols in `transaction` /
  `versions` are module-internal helpers (`_binding`, `_confirm_record`,
  `_round_lock`, `_refresh_log`, …) with no cross-module consumers.
- `server.py` keeps importing `_self_check_floor` — a self-check harness,
  not a shared primitive; it stays out of this change's scope.
