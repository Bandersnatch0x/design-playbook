---
description: Report Design I/O run phase, blocker, and next resume action
---

# run-status

Inspect a stopped Design I/O run without reconstructing state from scratch files by hand.

## Usage

```text
python <plugin>/scripts/run_status.py [.scratch/<run>] [--json] [--list] [--scratch <dir>]
```

- Omit the run path to pick the newest directory under `--scratch` (default `.scratch/`).
- `--json` emits machine-readable stages + `next` action, plus the continuation block: selected run, current phase, blocker, run integrity, and the Console capability receipt (`implementation` / `validation` / `availability` / `publicClaim`).
- `--list` only lists discovered runs.

For an eligible run the continuation names an explicit `open-console` command for the local, experimental, trial-gated Run Console — no authorized external trial or public release is claimed until the separately authorized read-only trial gate passes (ADR-0043). `run-status` never starts a server, daemon, or background process itself; an ineligible run reports the blocking reason and a safe fallback instead. On Windows the emitted command line is PowerShell syntax (single-quoted literals behind the `&` call operator) — paste it into PowerShell, not cmd.exe.

## Explicit frontend scope review

The source checkout also provides a bounded, read-only report for self-use. It
has no separate Console panel or persistent mapping, and no measured time-saving
or released-package claim.

```text
python <plugin>/scripts/run_status.py <run> --scope path:P1 --scope page:checkout
python <plugin>/scripts/run_status.py <run> --scope component:Retry --json
python <plugin>/scripts/run_status.py <run> --scope path:P1 --git-root <repo> --base-revision <base> --head-revision <head> --json
python <plugin>/scripts/run_status.py <run> --scope path:P1 --git-root <repo> --base-revision <base> --worktree --json
```

- A run path and at least one `--scope` are required. Scope mode does not discover
  runs and cannot combine with `--list`; `--scratch` only applies to discovery.
  Its JSON is a scope report, not the legacy status JSON or Run Snapshot v1. It
  carries `schemaVersion: 1`; every member of `evidence_gaps[].bindings[]` has the
  same keys `integrity`, `reasons`, `source`, `content_hash`, and an unbound or
  unreadable entry reports `source: null` / `content_hash: null` rather than
  dropping those keys.
- Repeated scopes accept `path:P1`, `page:<id>`, `component:<id>`, and
  `file:<relative/path>`. Paths must stay within the explicit Git root, or the
  selected run if no Git root was given. Absolute paths and traversal are rejected.
- Known links require an L3 `Path | Steps` row and an L6 `(path: P1)` reference.
  Page links additionally require an exact L2 `Page | Duty` entry and an exact
  step token separated by `->` or an arrow. Free-form prose is not a code
  dependency map. Assumptions stay `assumed`; component and file clues currently
  remain `unknown`. No association means unknown, never unaffected.
- Git is optional. When requested, supply the actual repository root, a base,
  and exactly one of a head revision or `--worktree`. Worktree mode includes
  untracked paths. The report neither guesses a base nor scans source code.

Evidence requirements are read only where an L6 item already declares a precise
continuation, for example:

```text
- Given checkout fails When retry is offered Then recovery is visible (path: P1)
  Required evidence: screenshot; state=error; viewport=390x844
```

The recognized proof values are `screenshot`, `a11y_tree`, and
`interaction_trace`; `state` and `viewport` are optional and appear in that order.
This optional read convention adds no mandatory spec field. Missing or
unrecognized prose stays `unknown`; conflicting declarations stay `inconsistent`.
The separate sampling summary enumerates only nonblank L5 state cells.
`reported` means a sampling claim, not a verified proof binding.

The report separates source availability, binding integrity, evidence gaps, and
the original evaluator result. Missing required proof is `blocked`; skipping the
evaluator remains `unaudited`. An owner ledger that exists but cannot be
projected is never read as an absent one: every gap gains the
`pointback-malformed` reason, and sources that are still current report the
evaluation as `inconsistent` rather than `unknown`. Binding timestamps order
by instant, so mixed `Z` / `+HH:MM` stamps pick the real latest capture: a
stamp that is missing, offset-less, or not ISO-8601 reports
`invalid-binding-timestamp`, and two distinct entries sharing the latest
instant report `conflicting-bindings`; both leave the binding `inconsistent`.
Not-applicable and unreviewed reasons are referenced at their source, not
copied as private prose.
It does not start a Provider, read browser login state, emit capture URLs or
source code, write run artifacts, or grant semantic approval. Treat scope names
and relative file paths as local data.

Reverification candidates retain the original Repair Packet's invalidated set,
owner, resume stage, and recapture requirement. **They cannot safely narrow the
original owner scope**: declaration links do not prove exhaustive code impact.
No repair or acceptance command is executed.

Before copying an owner command from an earlier report, repeat the same inputs
with its `source_hash`:

```text
python <plugin>/scripts/run_status.py <run> --scope path:P1 --expected-source-hash sha256:<previous-hash> --json
```

Changed or owner-unverified sources make the report `stale` and remove the copyable command.
Unavailable contracts also suppress it. Refresh the report and use the existing
owner workflow; a source check does not lock files against later edits.
Exit 0 means a report was produced, not that the run passed acceptance.
Invalid inputs or unreadable/out-of-root sources exit 2.

## Done when

The command names completed stage markers, any active blocker (preview floor, baseline gate, recirculate verdict), and the single next valid resume action. It reuses `validate_run` judgments for G5 confirm validity rather than inventing a second state machine. Stale, partial, hash-mismatched, malformed, or inconsistent runs stay visible as those states and are never replaced by an older successful snapshot.

In scope mode, known links are traceable to their declaration and hash, uncertain
links remain explicit, and diagnostic gaps never replace the evaluator verdict.
