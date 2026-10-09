# Offline visual-edit host

This is a real, source-backed host application for Preview integration tests,
not plugin runtime or a source-mapping service. It needs the repository's Python
package; the end-to-end tests also need the existing Playwright/Chromium
installation. No network service or model invocation is required.

The separate applier accepts `--user-id <local-display-id>` (default: a PID-based
label). Its existing exclusive **root-wide** lock is the only source-write
serialization authority: even disjoint edits are conservatively rejected.
The atomically published owner marker includes PID, identity, requested
selectors/properties and old/new values. A refusal includes the owner and exact
overlapping requested edits as `conflicts`; values describe the pending request,
not inferred source mappings or an already committed write. EOF/declined
confirmation releases that applier's own marker so the next process can review
and confirm normally. Crashed, corrupt or stale markers are never stolen.
The applier never authorizes source writes on its own; plugin `writesSource`
remains false and all existing source-hash, confirmation and rollback gates remain.

Copy `index.html`, `styles.css`, `palette.json` and `assets.json` into a disposable
host source directory, then
run `python packages/design-playbook/tests/fixtures/visual-edit-host/host.py
--root <host-source>`. The process prints its actual `127.0.0.1` route. The server
serves both files, embeds the plugin's `build_visual_edit_bridge_script()`, and
includes a hash of every declared local asset and the exact manifest bytes in
HTML for legacy artifact-only callers. With an explicit asset map, Preview reads
those source files directly: dynamic HTML re-renders do not invalidate a batch,
but a declared file or declaration change does. This dependency set is
**host-owned**, not linked-resource discovery by the plugin. `palette.json` is a declared local input, not a fetched third-party asset.

## Host-declared asset manifest

`assets.json` explicitly lists the host's local dependencies:

```json
{"assets": ["index.html", "styles.css", "palette.json"]}
```

The original two-file path remains available: without a manifest, the HOST's
explicit built-in set is exactly `index.html` and `styles.css`. There is no
filesystem scan or inference from HTML. With a manifest, every listed file must
exist, have a unique canonical local relative path, and remain inside the host
root without links. Both original files are required. URLs, parent traversal,
duplicates and the manifest itself (including filesystem case aliases) are
refused. The declaration bytes are automatically bound as metadata.

`assetHashes` covers every declared dependency plus `assets.json` when present,
including assets not selected by the candidate. These hashes participate in the
confirmation phrase as well as the host's route marker. Changing/removing a
listed asset, removing it from the manifest, extending the set, or removing the
manifest invalidates a pending batch or refuses apply. This is rechecked after
typing confirmation. An unlisted file does not enter the binding merely by being
created; adding it to the manifest changes the binding. No arbitrary discovery,
CDN fetching or real build pipeline is provided.

Open that live route through the existing Preview transaction using a separate
copy of `index.html` as its artifact. Preview owns the sandboxed iframe, pending
batch and durable `confirm-round-1.json`; it never writes the host's source.
Its confirmation stages the handoff and does **not** approve a host source write.

### File-content observation for dynamic dev servers

For an artifact next to `assets.json`, `observe_visual_source` hashes the exact
manifest and bytes of its named local files, plus the artifact digest and exact
loopback URL. The manifest must contain a nonempty `assets` list; optional host
metadata (such as selector mappings) is also bound through the manifest bytes.
The fixture's additional two-file requirements above remain host policy.

For a **detached** Preview artifact, place this explicit `visual-source.json`
beside that artifact (the host or caller creates it, never the plugin):

```json
{"sourceRoot": "D:/absolute/host", "assetMap": ".scratch/host-adapter/assets.json"}
```

`sourceRoot` must be an absolute unlinked directory and `assetMap` must resolve
to an unlinked file inside it; entries are canonical paths relative to that root.
A HOST adapter can use the equivalent keyword arguments
`observe_visual_source(prototype, route, source_root=host_root, asset_map=manifest)`.
Use the same artifact bytes and authoritative map on both sides; the sidecar
only locates the map and is not a second pending-batch authority. No source path
is accepted from HTTP, no assets are discovered or fetched, and nothing here
writes source. Malformed or missing explicit declarations fail visibly.

The route is still fetched on each observation and must return bounded
`text/html` successfully; redirects, failures and non-HTML responses still
refuse. Its dynamic body is not the primary hash when files are declared.
Without a sidecar, explicit arguments, or adjacent `assets.json`, legacy
artifact-plus-response binding remains unchanged. Thus a dynamic host must
supply its map rather than claim that an undeclared HTML snapshot binds source.

## Review and host confirmation

The coding agent reads the handoff and authors either a separate candidate CSS
file (the original single-file path), or a candidate directory whose relative
paths select existing HOST-declared UTF-8 source files, such as `index.html` and
`styles.css`. Candidates cannot edit the manifest or select unlisted assets.
The HOST applier compares supplied bytes; it does not generate them. Directory
candidates cannot create/delete source files or traverse source/candidate links.
Unselected source files are not written; selected files, including unchanged
members, are all included in the hash binding.

```text
python packages/design-playbook/tests/fixtures/visual-edit-host/applier.py review --root <host-source> --handoff <preview/confirm-round-1.json> --candidate <agent-candidate.css-or-directory> --route-url <printed-route>
python packages/design-playbook/tests/fixtures/visual-edit-host/applier.py apply --root <host-source> --handoff <preview/confirm-round-1.json> --candidate <agent-candidate.css-or-directory> --route-url <printed-route>
```

`review` prints one JSON record with one unified diff spanning the changed files,
`files[relativePath].beforeHash` / `afterHash` for every selected file, and an
`APPLY <digest>` phrase bound to the entire file set, exact bytes, diff, observed
source hash, route and batch hash. `apply` prints the diff again and requires
that exact phrase on stdin. EOF, `yes`, a wrong hash, stale inputs and swapped
candidates are refused. After confirmation the HOST re-reads the entire review;
a changed member or membership cannot ride an earlier approval.

## All-or-nothing application and rollback

The HOST keeps every selected file's pre-write bytes in memory. It stages **all**
candidate files beside their targets, flushes/fsyncs them, then commits via
per-file atomic replacement. A staging failure leaves source unchanged. A commit
failure restores every already-committed file and removes staged files. After
all commits it observes the real HTTP route again; failed post-write observation
restores **all** selected files, preserving exact bytes (including CRLF).
Every restore is attempted even if an earlier restore fails.

Success prints `outcome: applied`, all per-file hashes and the existing
before/after route, host and CSS hashes. Every handled failure exits 2 and writes
`REFUSED: <JSON>` to stderr, never an applied-success receipt. Diagnostics retain
`owner: host-applier`, `pluginWritesSource: false`, `status: error`, and `error`.
Write/lock failures additionally report `outcome: failed`, `phase`, `reason`,
`committedFiles`, `writeApplied`, `rollbackAttempted`, `rolledBack`, and
`rollbackErrors` keyed by file. With no writes, `rolledBack: true` means there
is no committed state to restore; `rollbackAttempted` remains false.

Observation failures also retain `observationFailed`, `observationError` and,
when restoration fails, `rollbackError` for the original single-file callers.
`writeApplied` records initial replacements, **not** successful completion.
`rolledBack: false` means restoration failed: inspect the named files and recover
through the HOST workflow. Restoring files does not claim the failed HTTP route
is healthy. No plugin artifact or pending handoff is updated by the applier.

All-or-nothing describes the completed operation and compensating restoration,
not simultaneous multi-file visibility to arbitrary readers. There is no durable
journal or guarantee through forced process termination; OS restore errors are
reported honestly rather than hidden behind an unconditional atomicity claim.

## Controlled in-fixture crash recovery

For local fault validation only, `apply --interrupt-at after-staging` aborts once
all candidate bytes are staged, before any commit. `apply --interrupt-at
after-first-commit` aborts immediately after the first replacement. Each raises a
dedicated fixture `BaseException`, not an ordinary write error; the commit owner
catches that explicit abort, restores all committed files and removes staged
files before exiting 2. The failed operation is never reported as applied.

The diagnostic retains the normal rollback fields and adds `phase: interruption`,
`faultPoint`, `reason: fixture-abort:<point>` and
`recoveryScope: controlled-fixture-abort-only`. After its own lock has actually
been released it reports `lockDisposition: owned-lock-released`. A new CLI
invocation can then acquire a fresh lock and retry against the unchanged binding.
If a different/residual lock exists, the existing fail-closed rules below still
apply; PID or age never authorizes lock stealing. Restoration failures remain
`rolledBack: false` with per-file errors, not a claim of no partial state.

Tests assert byte-exact pre-abort source state (including unselected dependencies
and no staged leftovers) and a successful restart for both points. This is
compensation for controlled in-fixture aborts, not `kill`, `os._exit`, power loss,
or OS/cross-process crash recovery. No partial state after successful compensation
does **not** claim concurrent readers can never see an intermediate replacement.

## Concurrent appliers and stale locks

Before review/confirmation, `apply` exclusively creates
`.<source-root-name>.applier.lock` beside the canonical source root, with an owner
marker (`owner`, process ID, random nonce, canonical source root). It holds the
lock through commit, observation and any rollback, then removes only its own
marker. A later applier fails immediately with `reason: applier-lock-exists`,
`phase: lock` and the existing `lockOwner`; it neither writes source nor removes
the first applier's lock. Standalone read-only `review` does not acquire it.

**Stale locks are not automatically stolen.** Active, stale, incomplete and
unreadable existing locks all fail closed; malformed markers report
`lockOwnerError`. Age and PID reuse cannot prove recovery is safe. Explicitly
inspect the owner and source state and confirm the original writer has stopped
before manually removing a stale lock. This is cooperative-applier exclusion,
not protection against unrelated editors or cross-process crash recovery.

## Scope and evidence

The 2026-10-03 ADR-0045 amendments, including round 2, authorize only this HOST
fixture and its tests. Real host framework/HMR integration and any real project's
build pipeline, third-party or CDN asset fetching/crawling, arbitrary asset
discovery, cross-process or OS-level crash guarantees beyond the fixture, any
plugin-side source writer, multiplayer/real-time collaboration (still Phase 2),
catalog submission and recruitment remain excluded.
Authorization and deterministic fixture tests are not a completion/release claim.
There is no HTTP write endpoint, new plugin writer or second batch authority.

```text
python -m pytest packages/design-playbook/tests/preview/test_visual_edit_host_assets_crash.py -q -s
python -m pytest packages/design-playbook/tests/preview/test_visual_edit_host_multifile.py -q -s
python -m pytest packages/design-playbook/tests/preview/test_visual_edit_host_e2e.py packages/design-playbook/tests/preview/test_visual_edit_host_failures.py -q -s
```

The tests use a real browser-created durable handoff and real HTTP. Candidate
bytes are explicitly deterministic test inputs, not a model invocation. The
multi-file tests use real CLI subprocesses for apply/concurrency, and intercept
only stdin/filesystem boundaries for fault injection; they verify byte-exact
restoration, all-files-staged-before-commit, unchanged plugin authority, hash-bound
confirmation, and explicit stale-lock handling. The six original single-file
fault paths and the original real-subprocess/G5 tests remain intact, including
source-write auditing, parent-only messages, one-time token, first-decision-wins,
and `sandbox="allow-scripts"` without `allow-same-origin`.
