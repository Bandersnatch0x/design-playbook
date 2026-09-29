# design-playbook-workbench

Local, single-maintainer design asset workbench. One Python process binds a
loopback-only HTTP listener, serves a build-free static UI (native ES modules,
no bundler), and owns its own SQLite state. It needs no Node, no model account,
and no development checkout.

Implements R01–R15 of the internal specification: the local entry point and
project registry, the asset library with immutable revisions, cross-project
reuse, design systems, components and pages, the single-user canvas and
orchestration, Agent-managed work requests, existing-owner evidence and
backflow, archive/trash/delete, consistent backup and restore, and the delivery
and quality bar.

## Requirements

- Python 3.12 or newer.
- A desktop browser. The UI is plain HTML/CSS/JS served by the service.
- No Node build step, no model credentials, no network access.

## Install and start

```text
python -m pip install design-playbook-workbench
design-playbook-workbench --data-dir %LOCALAPPDATA%\design-playbook-workbench
```

On POSIX the same command works with a `$HOME/.local/share` style path. From a
checkout, `python -m pip install .` inside this package installs the same
distribution.

Flags:

| Flag | Meaning |
| --- | --- |
| `--data-dir PATH` | Private state directory (default: the per-user application data directory). |
| `--bind-host HOST` | `127.0.0.1` (default) or `::1`. Nothing else is accepted. |
| `--port N` | TCP port; `0` (default) picks a free ephemeral port. |
| `--session-ttl-seconds N` | Session and bootstrap lifetime override. |
| `--version`, `--help` | Version and usage. |

Startup prints one JSON line with the **actual** bound origin, the preview
origin, the boot ID, the session expiry, the data directory, the credential
record path, and a one-time `bootstrapUrl`. Open that URL in a browser: the
fragment is exchanged for an in-memory session token and cleared from the
address bar, so it cannot be replayed, bookmarked, or read from storage. A
placeholder address is never printed — if the port is taken, startup fails.

### Stop

`Ctrl+C`, `SIGTERM`, or `SIGBREAK`. The service stops accepting requests and
deletes the credential record. Exit codes: `0` clean stop, `2` cannot bind the
requested address, `3` a `WorkbenchError` (for example an unusable data
directory).

### Restart

Every start mints a fresh boot ID, session token, and bootstrap secret, so all
previous sessions and Agent capabilities become invalid. Project registrations,
assets, revisions, proposals, and owner confirmations persist. A WorkRequest
in flight must be re-authorized and claimed again.

## Data directory

```text
<data-dir>/
  workbench.db      SQLite (WAL): projects, bindings, grants, assets, revisions,
                    mutations, proposals, journal, imports, requests, owners
  blobs/            content-addressed immutable carriers
  session/          the private credential record (current OS user only)
  staging/          proposal content and pre-state backups, outside all projects
  tmp/              same-volume temporary area for write transactions
```

The data directory must not sit inside, or contain, any registered project
directory. On POSIX it is created `0700` and the record `0600`; on Windows the
record gets an explicit ACL with inheritance removed and a single grant to the
current user. A record that cannot be made private is a hard startup failure.

## Diagnostics

- **Start line** — the JSON line above is the primary diagnostic: it names the
  live origin, boot ID, expiry, and record path. Copy the origin to probe
  reachability; the record path shows whether credentials were written.
- **`GET /api/v1/status`** — requires the session token (or a capability);
  without one it answers `401 unauthorized`, which is itself a useful
  diagnostic. With a credential it returns the schema version, the service
  name, the bound authority, and the session receipt (boot ID, expiry) as JSON.
  Use it to confirm a running service is the one you expect before trusting a
  UI session. The static shell (`GET /`) is the only read that needs no
  credential, and it carries no project data.
- **Rejections** — every error is a structured envelope with `code`,
  `operationId`, and a fixable message. No rejection echoes a path, secret, or
  traceback.
- **Disconnected projects** — reads re-probe every binding. A folder that moved,
  vanished, or was replaced shows `已断开` and blocks that project's operations
  until the maintainer confirms a rebind; same-name folders are never
  re-matched automatically.
- **Credential hygiene** — credentials never travel in a query string and are
  never written to the log, `localStorage`, or an export.

## Backup and restore

Backup, verify, and restore are **maintainer-only settings actions** (the
browser session; an Agent capability is refused). They are available from the
Settings panel and over the API.

```text
# create (seals a consistent snapshot and writes it to an absolute path;
# the service suggests workbench-<id>.dpwb.zip)
POST /api/v1/backup
{"action": "create", "destination": "<absolute archive path>",
 "operation": {"operationId": "...", "payload": {"action": "create"}}}

# verify an existing archive (read-only)
GET  /api/v1/backup?path=<absolute archive path>

# restore into a NEW directory (the original is left untouched)
POST /api/v1/backup
{"action": "restore", "path": "<absolute archive>", "target": "<absolute new dir>",
 "operation": {"operationId": "...", "payload": {"action": "restore"}}}
```

Properties that matter when you actually need this:

- **Consistent snapshot.** The database is copied through SQLite's backup API
  under the store lock (WAL-safe), and every blob is hashed into a manifest, so
  a backup cannot silently capture a half-written state.
- **No secrets, no source.** The manifest declares `containsCredentials: false`
  and `containsSourceRepo: false`; session records, tokens, and project source
  files are excluded. Archiving inside a registered project folder is refused.
- **Fail-closed verification.** The archive declares the format
  `design-playbook-workbench-backup/v1`. Verification rejects a non-archive, an
  unknown format, a schema newer than the running service, path escape (`..`,
  absolute entries), symlink entries, more than 100,000 files, more than
  20 GiB uncompressed, and any database or blob hash mismatch.
- **Restore writes elsewhere.** Restore extracts into a **new** empty directory
  and verifies referential integrity there. It reports `switched: false` and
  `reauthorizationRequired: true`: the original data directory is never
  modified, and the restored copy needs its own authorization. To adopt it,
  stop the service and restart with `--data-dir <the new directory>`.
- **No replay of unfinished work.** An interrupted apply journal is **not**
  replayed on restore (`journalsNotReplayed: true`); recovery remains an
  explicit maintainer decision in the restored instance.

## What the UI covers

Project entry (probe, confirm, register, rebind, grants, remove) · asset library
(import, search by name/tag, detail, capabilities, previews) · revisions and
publishing · reuse (reference, derive, copy, import closure, upgrade, rollback)
· change proposals (review, apply, recover, revert) · design systems (tokens,
baseline, validation) · components and pages (attributes, variants, slots,
distillation candidates) · the canvas (boards, nodes, gestures, undo history,
snapshots, compare, context selections) · work requests and Agent handoff ·
existing-owner projections, confirmations, and backflow · archive, trash,
restore, and reference-safe hard delete · settings, backup, and restore.

## Authority model

- The maintainer's browser session holds every decision: project
  administration, proposal approval and application, publishing, lifecycle,
  owner confirmation, and backup/restore.
- An Agent receives a capability bound to one project, one work request, and its
  declared operations. It can claim, heartbeat, return a result, or fail that
  request, and it may **submit** a proposal for the maintainer to approve. It
  cannot approve, apply, revert, publish, archive, delete, import, or drive the
  canvas.
- A capability must present **no** `Origin`; a browser write must present
  exactly the bound `Origin`. The two credential kinds are never mixed.
- The workbench never calls a model. Model credentials stay in the maintainer's
  own Agent host, and the workbench does not sandbox the host's OS behaviour.

## Acceptance tools

The repository carries operator tools for the acceptance items that need a real
host: a scale fixture builder, a browser-driven performance harness, a
clean-install smoke, and the two Agent handoff targets. See
[tools/README.md](tools/README.md).

## Develop and verify

```text
python -m pytest tests -q
python -m pytest tests/test_ui_browser.py -q     # needs Chromium (Playwright)
```

The suite runs a real loopback service over real temporary directories:
path/identity/alias rules, security negatives (non-loopback binds, forged
`Host`/`Origin`, replayed bootstrap, cross-project capabilities, credential
record permissions, log hygiene), mutation idempotency versus conflict,
migration refusal, proposal staging and authorized application with injected
mid-write failures, recovery rollback versus finish, canvas transactions and
undo limits, work-request leases, owner projections, archive/delete reference
safety, backup/restore refusals, packaging, and Chromium journeys across the
project, assets, proposals, design system, components, canvas, orchestration,
work request, owner backflow, lifecycle, and settings flows.
