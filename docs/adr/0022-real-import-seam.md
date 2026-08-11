# ADR-0022: Real import seam

## Status

Accepted (C5, 2026-08-09)

## Context

Cross-directory imports in the bundled Python surface were glued with
per-runtime `sys.path` adapters:

- `scripts/validate_run.py` inserts the Preview runtime dir and the Evidence
  runtime dir to import `integrity` / `capture_contract`.
- `scripts/run_status.py` (packaged copy + monorepo root copy, byte-identical)
  resolves `_PACKAGE_ROOT` and inserts the Preview runtime dir plus its own
  scripts dir.
- `mcp/preview/server.py` and `mcp/evidence/server.py` insert `mcp/` to reach
  `_transport`.
- The sibling launchers insert the target runtime dir before `runpy.run_path`.
- Tests insert their sibling runtime / scripts dirs to import flat modules.
- `scripts/vnext_live_dogfood.py` inserts `mcp/evidence` to import the server.
- `scripts/run_status.py` (root) is a byte-identical dev copy of the packaged
  one — a second drift surface maintained by hand.

31 `sys.path.insert` calls total; every new consumer had to rediscover which
directory to append. The package directories (`mcp/`, `mcp/preview/`,
`mcp/evidence/`) already carry `__init__.py`, but `design-playbook/` and
`design-playbook/scripts/` were not packages, so no absolute import worked.

## Decision

Make the Python surface a real package and give it one import seam:

- Add empty `packages/design-playbook/__init__.py` and
  `packages/design-playbook/scripts/__init__.py`.
- Every entry point (script with `__main__`, MCP server, test module, dev
  tool) runs the same guarded, idempotent bootstrap: put the package root
  (`packages/design-playbook`) on `sys.path` once, then use absolute
  `design_playbook.*` imports only.
- All internal sibling imports become package-absolute
  (`design_playbook.mcp.preview.control`, `design_playbook.scripts.stages`,
  …). No runtime module mutates `sys.path`.
- Delete the root `scripts/run_status.py` dev copy; the packaged copy is the
  single source. Root consumers (`tests/test_run_status.py`,
  `tests/test_stages_registry.py`) move to the packaged copy / absolute
  imports.
- Compatibility launchers (`packages/design-playbook-preview/server.py`,
  `packages/design-playbook-evidence/server.py`) keep their external
  behavior; they drop their own path insert and let the bundled server
  self-bootstrap.

## Consequences

- One import seam: a new consumer adds the same bootstrap block and imports
  absolutely; there are no more per-runtime path adapters to discover.
- `scripts/` becomes an importable package, so tests and dev tools import
  `design_playbook.scripts.*` instead of guessing directories.
- One `run_status.py`; no more byte-identical drift surface.
- Message texts and behavior are unchanged — this is a pure import-mechanics
  refactor; the full test suite and the seam test stay green.
