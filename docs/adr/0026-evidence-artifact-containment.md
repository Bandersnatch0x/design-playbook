# ADR-0026: Evidence artifact containment has one authority

## Status

Accepted (architecture second confirmation, 2026-08-11). Supersedes ADR-0018
only for artifact-path containment ownership; capture contract v1 remains in
force.

## Context

The Evidence Provider resolves a possibly nonexistent write target, while G6
resolves an existing artifact and requires a regular file. Both enforce the
same security invariant with separate implementations: an artifact path must
not escape the run's resolved `evidence/` subtree. Collapsing both callers into
one mode-driven helper would hide their different existence timing and error
contracts.

## Decision

Place artifact containment in one deep module under
`design_playbook.mcp.evidence`. Its interface exposes distinct write-target
and read-artifact operations backed by one private canonical containment
implementation.

At resolution time both operations reject `..`, native/POSIX/Windows absolute
paths, resolution failures, canonical escapes, and observed symlink escapes.
The write operation permits a nonexistent suffix and checks the existing
resolved prefix. The read operation additionally requires an existing regular
file. Failures return stable reason codes; the Provider and G6 map those codes
to their existing payloads, rule IDs, messages, and repair text.

The current threat model does not claim protection against a concurrent
untrusted filesystem actor replacing a parent directory or symlink between
resolution and write. If that threat enters scope, this module must own the
actual write through a directory-handle-based or equivalent
containment-preserving primitive; callers must not add another preflight check.

## Considered options

- Leave containment duplicated: rejected because security fixes can drift.
- Use one public helper with read/write mode flags: rejected because it hides
  existence timing and produces a shallow interface.
- Claim check-then-write closes TOCTOU: rejected because path resolution alone
  cannot make that guarantee.

## Consequences

Containment changes become local and reason-code behavior becomes testable.
Read and write callers retain their distinct compatibility surfaces. The
explicit threat-model limit prevents the shared module from overstating its
security guarantee. ADR-0039 adds `read_under` for arbitrary roots; the
evidence write/read operations and reason codes stay the contract surface.
