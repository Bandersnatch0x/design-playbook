# ADR-0046: Preview sessions must never share a loopback origin

Accepted as a correctness repair (2026-10-06). In scope under
[ADR-0045](0045-external-evidence-spend-gate.md) §2 ("bug fixes, security-gate
repairs ... remain in scope"), which gates new capability rather than
correctness; no exception amendment is required or claimed. Tightens the
listener contract introduced with the Preview decision transaction
([ADR-0013](0013-preview-decision-transaction.md)) and the loopback security
posture of [ADR-0038](0038-run-snapshot-contract-and-loopback-security.md).

## Context

`_bind_preview_server` in `mcp/preview/review_session.py` prefers a fixed
default port so the control shell keeps one origin across preview rounds and
`localStorage` (onboarding seen-flag, drafts) persists. The docstring states the
intended fallback: when that port is taken — a concurrent preview — bind an
ephemeral port instead.

That fallback never ran on Windows. `http.server.HTTPServer` sets
`allow_reuse_address` (SO_REUSEADDR), and Windows SO_REUSEADDR permits a bind to
a port another socket is actively listening on, so the second bind succeeded and
raised no `OSError`. Two live preview servers then shared one origin and both
reported the same `server_address[1]`.

Two consequences, one of them not benign:

- **Session isolation broke.** A browser pointed at the shared origin could be
  served the *other* session's control shell, whose iframe points at that
  session's live route. Observed as a host-suite adapter failure asserting the
  iframe `src` equalled the expected route while holding two different loopback
  ports.
- **Submissions could reach the wrong session.** The control form POSTs the
  decision token and round to the shared origin, where either server may accept
  it. First-decision-wins and the one-time token still reject a *stale* or
  *mismatched* attempt, but the wrong session becomes an eligible recipient —
  a boundary failure, not merely flaky tests.

The defect is platform-conditional, which is why it survived: POSIX SO_REUSEADDR
already refuses a port a live listener holds, so the documented fallback works
there and the Windows behaviour went unexercised until concurrent previews ran
on Windows.

## Decision

1. **A preview listener binds exclusively wherever reuse would alias a live
   peer.** `_PreviewHTTPServer` sets `allow_reuse_address = os.name != "nt"`.
   On Windows a taken port raises `OSError`, so the documented ephemeral
   fallback runs; on POSIX behaviour is unchanged, where reuse is safe and
   TIME_WAIT rebinding is preserved.
2. **The fixed default port is an optimization, never a shared origin.** One
   origin across rounds is a convenience for `localStorage`; two sessions
   sharing an origin is a defect. A port still in TIME_WAIT on Windows also
   falls back to ephemeral — the safe direction.
3. **The property is pinned by a test, not by the platform.** A regression test
   asserts that two concurrently bound preview servers never report the same
   port. It fails on the defect (`4619 == 4619`) and passes with the fix.
4. **Cross-session isolation is a preview correctness property.** Any future
   preview listener, launcher, or compatibility shim must preserve it. Test
   flakiness was the messenger; the boundary is the subject.

## Consequences

- Concurrent previews on Windows now get distinct origins, which is the
  intended behaviour and the reason the fallback exists. A developer who relied
  on the fixed port being available during a concurrent run loses origin
  persistence for that run; correctness wins.
- The fallback path is now reachable on Windows, so it carries real traffic
  there and must stay correct.
- Evidence at acceptance: class-level probe — `allow_reuse_address=True` binds
  `4619 / 4619` (aliased), `False` raises on the second bind; the new regression
  test is RED on the defect and GREEN with the fix; four-way parallel presence
  runs went from 0/12 clean to 12/12 clean; the full preview suite passed at
  390 passed / 43 subtests with `validate`, doc links, and Ruff clean.
- Not addressed here, recorded honestly: the same investigation found the
  preview suite writing round-ledger files into the user-level
  `~/.design-playbook/preview-ledger` (3966 of 3974 entries bound to no live
  preview directory, now session-isolated by `tests/preview/conftest.py` and
  archived). That is test hygiene with its own commit, not this decision.
